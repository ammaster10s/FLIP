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
# The tutorial skills are a tree: `.claude/skills/new-tutorial/` routes into `new-tutorial-*`
# sub-skills by the axes in fl-tutorials/specs/profile.yaml, and each sub-skill explains one spec
# file. Three things must agree or a route goes nowhere: the leaves on disk, the skills the profile
# names, and the skills the router's table lists. Claude Code discovers skills only as direct
# children of .claude/skills/ and blocks the Skill tool on `disable-model-invocation`, so a leaf is
# hidden from the `/` menu with `user-invocable: false` and nothing else.

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

FL_TUTORIALS = Path(__file__).resolve().parents[1]
REPO_ROOT = FL_TUTORIALS.parent
SPECS_DIR = FL_TUTORIALS / "specs"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
PROFILE = yaml.safe_load((SPECS_DIR / "profile.yaml").read_text(encoding="utf-8"))
ROUTER = SKILLS_DIR / PROFILE["router"]
ROUTER_TEXT = (ROUTER / "SKILL.md").read_text(encoding="utf-8")
SPECS = {
    p.name: yaml.safe_load(p.read_text(encoding="utf-8")) for p in SPECS_DIR.glob("*.yaml") if p.name != "profile.yaml"
}
RULE_IDS = {rule["id"] for spec in SPECS.values() for rule in spec["rules"]}
PREFIXES = "|".join(sorted(spec["id"] for spec in SPECS.values()))
CITED_RULE = re.compile(rf"\b((?:{PREFIXES})-\d{{2}})\b")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
LEAVES = sorted(SKILLS_DIR.glob("new-tutorial-*/SKILL.md"))
DESCRIPTION_CAP = 1536  # Claude Code truncates a skill's listing entry beyond this


def _frontmatter(path: Path) -> dict[str, str]:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match, f"{path} has no YAML frontmatter"
    return dict(re.findall(r"^([\w-]+):\s*(.*)$", match.group(1), re.M))


def test_router_is_the_user_facing_skill():
    fields = _frontmatter(ROUTER / "SKILL.md")
    assert fields["name"] == PROFILE["router"]
    assert fields.get("user-invocable") != "false"
    assert fields.get("disable-model-invocation") != "true"
    assert len(fields["description"]) <= DESCRIPTION_CAP


@pytest.mark.parametrize("skill", LEAVES, ids=lambda p: p.parent.name)
def test_leaf_is_router_reachable_and_hidden_from_the_menu(skill: Path):
    fields = _frontmatter(skill)
    assert fields["name"] == skill.parent.name, "a skill's name must equal its directory name"
    assert fields.get("user-invocable") == "false", "leaves are reached from the router, not the / menu"
    assert fields.get("disable-model-invocation") != "true", (
        "that flag blocks the Skill tool, so the router could not load it"
    )
    assert "new-tutorial router" in fields["description"]
    assert len(fields["description"]) <= DESCRIPTION_CAP


def test_leaves_on_disk_profile_and_router_table_agree():
    on_disk = {p.parent.name for p in LEAVES}
    in_profile = {entry["skill"] for mapping in PROFILE["specs"].values() for entry in mapping.values() if entry}
    in_router = set(re.findall(r"`(new-tutorial-[a-z-]+)`", ROUTER_TEXT))
    assert on_disk == in_profile, f"leaves vs profile.yaml: {on_disk ^ in_profile}"
    assert on_disk == in_router, f"leaves vs the router's table: {on_disk ^ in_router}"


@pytest.mark.parametrize("skill", LEAVES, ids=lambda p: p.parent.name)
def test_leaf_and_its_spec_name_each_other(skill: Path):
    specs_for_leaf = [name for name, spec in SPECS.items() if spec["skill"] == skill.parent.name]
    assert specs_for_leaf, f"no spec names {skill.parent.name}"
    text = skill.read_text(encoding="utf-8")
    for name in specs_for_leaf:
        assert name in text, f"{skill.parent.name} does not point at fl-tutorials/specs/{name}"


def test_common_spec_belongs_to_the_router():
    assert SPECS["common.yaml"]["skill"] == PROFILE["router"]


@pytest.mark.parametrize(
    "doc", [ROUTER / "SKILL.md", *ROUTER.glob("references/*.md"), *LEAVES], ids=lambda p: str(p.relative_to(SKILLS_DIR))
)
def test_every_cited_rule_id_exists(doc: Path):
    cited = set(CITED_RULE.findall(doc.read_text(encoding="utf-8")))
    assert cited <= RULE_IDS, f"{doc.relative_to(REPO_ROOT)} cites unknown rules: {sorted(cited - RULE_IDS)}"


def test_router_cites_every_reference_file_and_the_checker():
    references = sorted((ROUTER / "references").glob("*.md"))
    assert references, "the router has no references/"
    for reference in references:
        assert f"references/{reference.name}" in ROUTER_TEXT, f"router never points at {reference.name}"
    assert "make -C fl-tutorials check-tutorial" in ROUTER_TEXT
    assert not (ROUTER / "scripts").exists(), "the bash checker moved to fl-tutorials/specs/check_tutorial.py"
