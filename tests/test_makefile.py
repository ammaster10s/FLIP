# Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""The root Makefile's site upgrade verb is gated and data-safe (FLIP#1204), and the hub-only
bring-up creates every network it needs (FLIP#1344).

`make upgrade-onprem-trust` must run the readiness checklist and then reach the trust-level
upgrade, never the first-install steps (`ensure-seeded` re-seeds OMOP / Orthanc, `xnat-reset`
wipes the XNAT archive and database).

Usage:
    python3 tests/test_makefile.py
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_dry_run import REPO, assert_data_safe, dry_run, main  # noqa: E402

HUB_ONLY_SERVICES = {"flip-db", "flip-api"}  # what `make central-hub` starts (flip-api/Makefile `up`)


def hub_only_networks() -> set[str]:
    """The unprefixed names of the external networks HUB_ONLY_SERVICES join in the dev compose.

    Read from the file rather than listed here, so a network added to either service fails the
    test instead of breaking `make central-hub` on a fresh host again. Line-based: the root tests
    are stdlib-only (no PyYAML on the runner).
    """
    keys: set[str] = set()
    names: dict[str, str] = {}
    section = entry = None
    in_networks = False
    for line in (REPO / "deploy" / "compose.development.yml").read_text().splitlines():
        if top := re.match(r"^([\w-]+):", line):
            section, entry = top[1], None
        elif key := re.match(r"^  ([\w-]+):\s*$", line):
            entry, in_networks = key[1], False
        elif section == "services" and entry in HUB_ONLY_SERVICES:
            if re.match(r"^    networks:\s*$", line):
                in_networks = True
            elif in_networks and (item := re.match(r"^      - ([\w-]+)", line)):
                keys.add(item[1])
            elif re.match(r"^    \S", line):
                in_networks = False
        elif section == "networks" and (name := re.match(r"^    name: \$\{FLIP_INSTANCE:[^}]*\}(\S+)", line)):
            names[entry] = name[1]
    return {names[key] for key in keys}


class UpgradeOnpremTrust(unittest.TestCase):
    def test_upgrade_onprem_trust_is_gated_and_data_safe(self):
        out = dry_run("upgrade-onprem-trust", "TAG=v0.6.0", "YES=1", subdir=".")
        assert "onboard_onprem_trust.py" in out, out  # the readiness checklist gates it
        assert "site_upgrade.py plan" in out, out
        assert "--tag v0.6.0" in out, out
        assert "--yes" in out, out
        gate = next(line for line in out.splitlines() if "onboard_onprem_trust.py" in line)
        assert "--gate" in gate, gate  # the gate must not suggest up-onprem-trust
        assert "--kit-file" in gate, gate
        assert ".env.SCR.production" in gate, gate
        assert "_upgrade-trust-apply" in out, out
        assert_data_safe(out, "upgrade-onprem-trust")


class CentralHubNetworks(unittest.TestCase):
    def test_the_compose_file_is_still_parsed(self):
        assert "deploy_central-hub-network" in hub_only_networks(), hub_only_networks()

    def test_create_networks_centralhub_creates_every_hub_only_network(self):
        """`make central-hub` on a fresh host must not need the trust Makefile's `create-networks`."""
        for instance in ("", "kc"):
            out = dry_run("create-networks-centralhub", f"FLIP_INSTANCE={instance}", subdir=".")
            for network in hub_only_networks():
                name = f"{instance}-{network}" if instance else network
                assert f"docker network create --driver bridge {name}" in out, f"{name}:\n{out}"

    def test_remove_networks_removes_them(self):
        out = dry_run("remove-networks", "FLIP_INSTANCE=kc", subdir=".")
        for network in hub_only_networks():
            assert f"kc-{network}" in out, f"kc-{network}:\n{out}"


ENVIRONMENTS = (
    (None, "production"),
    ("true", "production"),
    ("stag", "stag"),
    ("lza", "lza-prod"),
    ("lza-stag", "lza-stag"),
)
KIT = (
    "FL_BACKEND=nvflare\n"  # Synthetic kit values; no credentials.
    "FL_KIT_SLOT=Trust_9\n"
    "FL_KIT_SLOT_NUMBER=9\n"
    "NUM_AVAILABLE_GPUS=0\n"
    "XNAT_AETITLE=XNAT\n"
)


class MakeKitSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for rel in (
            "Makefile",
            "deploy/env_mode.mk",
            "deploy/fl_backend.mk",
            "deploy/instance.mk",
            "trust/Makefile",
            "trust/xnat/Makefile",
            "trust/xnat/.env",
        ):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, target)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        uv = bin_dir / "uv"
        uv.write_text(
            f"#!{sys.executable}\nimport json, os, sys\n"
            "with open(os.environ['ARGS_FILE'], 'w') as out: json.dump(sys.argv[1:], out)\n"
        )
        uv.chmod(0o755)
        self.args_file = self.root / "args.json"
        self.env = {
            key: value for key, value in os.environ.items() if key not in {"PROD", "KIT", "KIT_FILE", "MAKEFLAGS"}
        }
        self.env.update(PATH=f"{bin_dir}:{os.environ['PATH']}", ARGS_FILE=str(self.args_file))

    def run_make(self, target, prod=None, *extra, dry=False, subdir="."):
        command = [
            "make",
            "--no-print-directory",
            *(["-n"] if dry else []),
            "-C",
            str(self.root / subdir),
            target,
            "KIT=SITE",
        ]
        if prod is not None:
            command.append(f"PROD={prod}")
        result = subprocess.run(command + list(extra), env=self.env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    def check_selected(self, expected, prod=None, *extra, subdir="."):
        self.run_make("onboard-onprem-trust", prod, *extra, subdir=subdir)
        args = json.loads(self.args_file.read_text())
        assert args[:4] == ["run", "--no-config", "../scripts/onboard_onprem_trust.py", "SITE"], args
        assert Path(args[args.index("--kit-file") + 1]) == self.root / "trust" / expected, args

    def test_suffixed_kit_wins_over_legacy_in_every_onprem_environment(self):
        (self.root / "trust/.env.SITE").write_text(KIT)
        for prod, suffix in ENVIRONMENTS:
            with self.subTest(prod=prod):
                filename = f".env.SITE.{suffix}"
                (self.root / "trust" / filename).write_text(KIT)
                self.check_selected(filename, prod)

    def test_legacy_kit_is_the_fallback_in_every_onprem_environment(self):
        (self.root / "trust/.env.SITE").write_text(KIT)
        for prod, _ in ENVIRONMENTS:
            with self.subTest(prod=prod):
                self.check_selected(".env.SITE", prod)

    def test_a_missing_kit_is_still_passed_to_the_checklist_for_diagnostics(self):
        self.check_selected(".env.SITE")

    def test_a_development_kit_cannot_override_the_onprem_production_default(self):
        (self.root / "trust/.env.SITE.development").write_text(KIT)
        (self.root / "trust/.env.SITE.production").write_text(KIT)
        self.check_selected(".env.SITE.production")
        self.check_selected(".env.SITE.development", subdir="trust")

    def test_explicit_kit_file_override_reaches_the_checklist(self):
        (self.root / "trust/.env.SITE.production").write_text(KIT)
        (self.root / "trust/operator-kit").write_text(KIT)
        self.check_selected("operator-kit", None, "KIT_FILE=operator-kit")

    def test_both_gate_callers_and_the_deployment_use_the_same_file(self):
        for filename in (".env.SITE.production", ".env.SITE"):
            with self.subTest(filename=filename):
                kit_file = self.root / "trust" / filename
                kit_file.write_text(KIT)
                for target in ("up-onprem-trust", "upgrade-onprem-trust"):
                    output = self.run_make(target, dry=True)
                    gate = next(line for line in output.splitlines() if "onboard_onprem_trust.py" in line)
                    args = shlex.split(gate)
                    assert "--gate" in args, gate
                    assert Path(args[args.index("--kit-file") + 1]) == kit_file, gate
                    if target == "upgrade-onprem-trust":
                        plan = next(line for line in output.splitlines() if "site_upgrade.py plan" in line)
                        plan_args = shlex.split(plan)
                        assert plan_args[plan_args.index("--kit-file") + 1] == filename, plan
                    else:
                        assert f"Using kit file trust/{filename}" in output, output
                kit_file.unlink()


if __name__ == "__main__":
    main()
