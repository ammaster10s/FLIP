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
"""The Makefile checks every argument before it goes into a Run Command script (FLIP#1390).

Run Command hands its script to a shell on the node, so a value is parsed as shell there before
flip-node's own checks run. These tests run the real targets with `az` stubbed on PATH and read
back what would have been sent to the node.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import AZURE_DIR

STUB_AZ = """#!/bin/bash
printf '%s\\n' "$*" >> "$AZ_LOG"
case "$1 $2" in
    "account show") echo 00000000-0000-0000-0000-000000000000 ;;
    "vm run-command") echo ok ;;
esac
"""


def _make(tmp_path: Path, target: str, **variables: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    az = bin_dir / "az"
    az.write_text(STUB_AZ)
    az.chmod(az.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "az.log"
    log.touch()
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "AZ_LOG": str(log)}
    args = [f"{k}={v}" for k, v in {"AZ_SUBSCRIPTION": "trial", **variables}.items()]
    result = subprocess.run(
        ["make", "-s", "-C", str(AZURE_DIR), target, *args],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, log.read_text().splitlines()


def _sent(calls: list[str]) -> list[str]:
    return [c.split("--scripts ", 1)[1].split(" --query", 1)[0] for c in calls if c.startswith("vm run-command")]


@pytest.mark.parametrize(
    ("target", "variables", "sent"),
    [
        ("reprovision", {"REF": "v0.12.0"}, "flip-node reprovision v0.12.0"),
        ("reprovision", {"REF": "0123456789abcdef0123456789abcdef01234567"}, None),  # pragma: allowlist secret
        ("reprovision", {}, "flip-node reprovision "),
        ("selftest", {"FL_BACKEND": "flower"}, "flip-node selftest flower"),
        ("join", {"NAME": "flip-trust-kit-AZ1.tar.gz", "KIT": "AZ1", "PROD": "lza-stag"}, None),
        ("logs", {}, "flip-node logs flip-provision 80"),
        ("report", {"FL_BACKEND": "nvflare"}, "flip-node report nvflare"),
    ],
)
def test_a_valid_argument_reaches_the_node(tmp_path, target, variables, sent):
    result, calls = _make(tmp_path, target, **variables)

    assert result.returncode == 0, result.stdout + result.stderr
    scripts = _sent(calls)
    assert len(scripts) == 1, calls
    if sent is not None:
        assert scripts[0] == sent


@pytest.mark.parametrize(
    ("target", "variables", "bad"),
    [
        ("reprovision", {"REF": "v0.12.0; touch PWNED"}, "REF"),
        ("reprovision", {"REF": "main"}, "REF"),
        ("selftest", {"FL_BACKEND": "nvflare`touch PWNED`"}, "FL_BACKEND"),
        ("join", {"NAME": "kit.tar.gz; touch PWNED", "KIT": "AZ1", "PROD": "lza-stag"}, "NAME"),
        ("join", {"NAME": "kit.tar.gz", "KIT": "AZ1 x", "PROD": "lza-stag"}, "KIT"),
        ("join", {"NAME": "kit.tar.gz", "KIT": "AZ1", "PROD": "lza-stag'; touch PWNED; '"}, "PROD"),
        ("logs", {"UNIT": "flip-provision; touch PWNED"}, "UNIT"),
        ("logs", {"LINES": "80 && touch PWNED"}, "LINES"),
        ("report", {"FL_BACKEND": "both"}, "FL_BACKEND"),
    ],
)
def test_an_unsafe_argument_never_reaches_the_node(tmp_path, target, variables, bad):
    sentinel = str(tmp_path / "PWNED")
    result, calls = _make(tmp_path, target, **{k: v.replace("PWNED", sentinel) for k, v in variables.items()})

    assert result.returncode != 0
    assert f"{bad}=" in result.stdout + result.stderr, "the refusal names the argument"
    assert not _sent(calls), "nothing was sent to the node"
    assert not (tmp_path / "PWNED").exists(), "the value was never run as a command locally either"
