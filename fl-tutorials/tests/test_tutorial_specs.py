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
# The tutorial contract lives in fl-tutorials/specs/ (YAML rules selected per tutorial by its
# tutorial.yaml manifest, run by specs/check_tutorial.py). This guard keeps the specs well formed,
# every tutorial's manifest valid, and every static MUST rule green across the catalogue — so a
# requirement a static check can see is enforced on every PR, not only when someone runs
# `make -C fl-tutorials check-tutorial`. Heavy rules (the guard suites, the sync script, `make
# export`) are skipped here because the rest of this suite and CI already run them.

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

FL_TUTORIALS = Path(__file__).resolve().parents[1]
SPECS_DIR = FL_TUTORIALS / "specs"
CHECKER = SPECS_DIR / "check_tutorial.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_tutorial", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module  # dataclasses resolve `from __future__ import annotations` through sys.modules
    spec.loader.exec_module(module)
    return module


checker = _load_checker()
PROFILE = checker.load_profile()
SPEC_FILES = checker.load_specs()
TUTORIALS = checker.discover_tutorials()
RULE_ID = re.compile(r"^[A-Z]{2,6}-\d{2}$")


def _tutorial_id(tutorial) -> str:
    return f"{tutorial.backend}:{tutorial.name}"


# --- the specs themselves --------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SPEC_FILES))
def test_spec_is_well_formed(name: str):
    spec = SPEC_FILES[name]
    assert spec["id"].isupper(), name
    assert spec["title"], name
    assert spec["skill"].startswith("new-tutorial"), name
    ids = [rule["id"] for rule in spec["rules"]]
    assert len(ids) == len(set(ids)), f"{name}: duplicate rule ids"
    for rule in spec["rules"]:
        assert RULE_ID.match(rule["id"]), f"{name}: {rule['id']}"
        assert rule["id"].startswith(spec["id"] + "-"), f"{name}: {rule['id']}"
        assert rule["level"] in checker.LEVELS, rule["id"]
        assert rule["statement"].strip(), rule["id"]
        check = rule["check"]
        assert check["type"] in checker.CHECKS, f"{rule['id']}: unknown check type {check['type']!r}"
        if check["type"] == "builtin":
            assert check["name"] in checker.BUILTINS, f"{rule['id']}: unknown builtin {check['name']!r}"
        assert all(isinstance(field, str) for field in rule.get("when", {})), rule["id"]


def test_rule_ids_are_unique_across_specs():
    ids = [rule["id"] for spec in SPEC_FILES.values() for rule in spec["rules"]]
    assert len(ids) == len(set(ids))


def test_profile_maps_every_axis_value_to_a_spec_and_its_skill():
    assert checker.COMMON_SPEC in SPEC_FILES
    assert set(PROFILE["specs"]) == set(PROFILE["axes"]) == set(checker.AXIS_FIELDS)
    for axis, values in PROFILE["axes"].items():
        mapping = PROFILE["specs"][axis]
        assert set(mapping) == set(values), f"profile.yaml specs.{axis} does not cover axes.{axis}"
        for value, entry in mapping.items():
            if entry is None:
                continue
            assert entry["spec"] in SPEC_FILES, f"{axis}.{value} -> {entry['spec']} is not a spec file"
            assert SPEC_FILES[entry["spec"]]["skill"] == entry["skill"], (
                f"{axis}.{value}: spec and profile disagree on the skill"
            )


def test_every_spec_is_reachable_from_the_profile():
    mapped = {checker.COMMON_SPEC} | {e["spec"] for m in PROFILE["specs"].values() for e in m.values() if e}
    assert mapped == set(SPEC_FILES), f"unreachable or missing spec files: {mapped ^ set(SPEC_FILES)}"


# --- the manifests ------------------------------------------------------------------------------


def test_every_tutorial_directory_has_a_manifest():
    assert TUTORIALS, "no tutorials discovered"
    missing = [t.relpath for t in TUTORIALS if not (t.path / checker.MANIFEST_NAME).is_file()]
    assert not missing, f"tutorial.yaml missing in: {missing}"


@pytest.mark.parametrize("tutorial", TUTORIALS, ids=_tutorial_id)
def test_manifest_is_a_valid_profile(tutorial):
    assert checker.manifest_errors(tutorial, PROFILE, SPEC_FILES) == []


def test_waivers_carry_a_tracking_reference():
    for tutorial in TUTORIALS:
        for rule_id, reason in (tutorial.manifest.get("waivers") or {}).items():
            assert "#" in reason, f"{tutorial.relpath} waives {rule_id} without naming an issue"


# --- the static contract, catalogue-wide ---------------------------------------------------------


@pytest.mark.parametrize("tutorial", TUTORIALS, ids=_tutorial_id)
def test_static_must_rules_hold(tutorial):
    outcomes = checker.evaluate(tutorial, PROFILE, SPEC_FILES, static_only=True)
    assert outcomes, "no rule applied"
    failed = [f"{o.rule_id} ({o.spec}): {o.statement} — {o.detail}" for o in outcomes if o.status == "fail"]
    assert not failed, "\n".join(failed)


def test_checker_refuses_an_unknown_tutorial_naming_the_marker():
    result = subprocess.run(
        [sys.executable, str(CHECKER), "does_not_exist", "--static-only"], capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "discovery marker" in result.stderr
