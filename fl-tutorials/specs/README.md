<!--
    Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
-->

# The tutorial contract, as specs

What a FLIP tutorial must satisfy is written here once, as YAML **specs**: one rule per
requirement, each with an id, a level and a check. A tutorial declares its **profile** in a
`tutorial.yaml` manifest at its root; `profile.yaml` maps each profile value to the spec that
applies; `check_tutorial.py` evaluates every applicable rule and reports under the rule's id.
The agent skills under `.claude/skills/new-tutorial*` explain the *why* and the traps behind
these rules and cite the ids; the specs are the *what*, and they are what CI runs.

```bash
make -C fl-tutorials check-tutorial TUTORIAL=<name> [FL_BACKEND=nvflare|flower]   # one tutorial (both backends by default)
make -C fl-tutorials check-all-tutorials                                           # the catalogue
```

The checker never runs the simulator — that is the only thing that proves a tutorial trains, and
it needs the dataset and (for imaging) a GPU: `make -C fl-tutorials run-tutorial TUTORIAL=<name>`.

## Files

| File | Rule prefix | Applies when |
|------|-------------|--------------|
| `profile.yaml` | — | the axes, their values, and value → spec / sub-skill |
| `common.yaml` | `COMMON` | every tutorial |
| `backend-nvflare.yaml` | `NVF` | `backend: nvflare` |
| `backend-flower.yaml` | `FLWR` | `backend: flower` |
| `data-imaging.yaml` | `IMG` | `data: imaging_2d` or `imaging_3d` |
| `data-tabular.yaml` | `TAB` | `data: tabular` |
| `model-deep-learning.yaml` | `DL` | `model: deep_learning` |
| `model-statistical.yaml` | `STAT` | `model: statistical` |
| `loop-evaluation.yaml` | `EVAL` | `loop: evaluation` |
| `loop-training-variants.yaml` | `TRV` | `loop: fine_tune`, `fed_opt` or `two_stage` |
| `datasets.yaml` | `DATA` | every tutorial; the tier picks the rules |
| `check_tutorial.py` | — | the checker (`--all`, `--backend`, `--static-only`, `--json`) |

## The manifest (`tutorial.yaml`)

One per tutorial directory, beside `README.md` — never inside `app/` or `app_files/`, which are
what the user uploads. Copy the nearest tutorial's and edit:

```yaml
name: ehr_risk_prediction          # = the directory name (same on both backends)
backend: nvflare                   # nvflare | flower — must match where the file sits
data: tabular                      # imaging_2d | imaging_3d | tabular
model: deep_learning               # deep_learning | statistical
loop: standard                     # standard | evaluation | fine_tune | fed_opt | two_stage | statistics_fedavg
job_type: standard                 # must match .env.app JOB_TYPE / app/config.json job_type
twin: flower                       # the other backend's copy, or null
dataset: {name: synthea, tier: public, target: download-synthea-data}   # target resolves at the fl-tutorials root
platform: {has_imaging: false, e2e_target: e2e_smoke_ehr, demo_profile: ehr}  # e2e_target / demo_profile may be null
simulator: {device: cpu}           # cpu | gpu
# optional:
query_from: null                   # name of the tutorial whose query.sql this one reuses (evaluation twins, the LDM)
weights_target: null               # Makefile target that stages a checkpoint host-side (download-checkpoints, prepare-checkpoint, weights)
waivers:                           # rule id -> reason; a waived failure is reported, never silent
  FLWR-12: "known drift, tracked on #1444"
```

`COMMON-01` validates the manifest against `profile.yaml` (enums, name and backend against the
tree, every waiver naming a real rule with a reason).

## The rule schema

```yaml
id: TAB                              # the file's prefix
title: Tabular / OMOP-only tutorials
skill: new-tutorial-tabular          # the sub-skill that explains these rules
applies_when: {data: tabular}        # documentation; profile.yaml is what selects the file
rules:
  - id: TAB-02
    level: MUST                      # MUST fails the check; SHOULD warns
    statement: The platform project has imaging off (manifest platform.has_imaging false)
    why: with imaging on the hub dispatches CREATE_IMAGING and the run dies at the image-pull wait
    enforced_by: ...                 # optional: the guard test or service that is the real enforcement
    when: {platform.e2e_target: '*'} # optional: dotted manifest field -> value | [values] | '*' (any non-null) | null
    check: {type: manifest, field: platform.has_imaging, equals: false}
```

Levels: a failing **MUST** fails the run; a failing **SHOULD** is a warning; a `manual` check is
listed for the reviewer (ⓘ) and never fails; a rule the manifest **waives** is shown as ⏭ with
its reason; a waived rule that **passes** is reported as a warning naming the stale waiver, so remove it.
The catalogue passes when no MUST fails.

### Check types

Paths are relative to the tutorial directory unless absolute; `{name}`, `{backend}`, `{job_type}`,
`{tutorial_dir}`, `{app_dir}`, `{repo_root}`, `{fl_tutorials}`, `{twin}`, `{e2e_target}`,
`{demo_profile}`, `{dataset_name}`, `{dataset_target}`, `{weights_target}`, `{query_from}` are
interpolated into paths, patterns and commands (double any literal brace in a regex: `{{0,300}}`).

| `type` | Fields | Passes when |
|--------|--------|-------------|
| `file_exists` | `path` (+ `glob: true`) | the path (or a glob match) exists |
| `file_absent` | `path` | it does not |
| `file_regex` / `file_not_regex` | `path`, `pattern`, `ignore_case` | the file matches / does not (multiline) |
| `files_regex` | `glob`, `pattern`, `expect: all\|any\|none` | all / any / none of the matching files contain the pattern |
| `json_key` / `toml_key` | `path`, `key` (dotted), `equals`, `in`, `min`, `value_type: int`, `absent` | the key satisfies the constraints |
| `byte_identical` | `path`, `template` (repo-relative) | the two files are identical |
| `manifest` | `field`, `equals`, `in`, `not_null`, `is_null` | the manifest field satisfies them |
| `make_target` | `makefile_dir`, `target` or `target_from` | `make -n` resolves it (null target passes) |
| `case_entry` | `path` | `sim-tutorial.sh` has a `case` arm for the tutorial |
| `builtin` | `name` | see `BUILTINS` in the checker (manifest_valid, required_files, twin_exists, demo_profile_*, git_ignored, …) |
| `pytest` | `files` | the guard files pass — **heavy** |
| `shell` | `cmd`, `cwd` | exit 0 — **heavy** |
| `manual` | — | always listed, never fails |

A heavy command that does not interpolate the tutorial (the guard suites, the sync script) runs once per
invocation, however many tutorials `--all` covers. `--static-only` skips the heavy types; that is what `tests/test_tutorial_specs.py` runs over
every tutorial in CI, so a MUST that a static check can see is enforced on every PR.

## Adding a rule, a value or a category

- **A rule**: add it to the spec whose `applies_when` fits, with the next free id. Say *why* in
  the rule or in the sub-skill. Prefer a static check; put the enforcement that already exists
  (a guard test) in `enforced_by` rather than duplicating it.
- **An axis value** (a new data modality, loop): add it to `axes` and `specs` in `profile.yaml`,
  then either map it to an existing spec or add a spec file and the sub-skill it names.
  `tests/test_new_tutorial_skill_tree.py` fails until the skill exists and the router lists it.
- **A waiver** is for a documented exception, never for a gap: say what is tracked where.

Precedent for YAML contracts in this tree: `datasets/utils/schemas/*.yaml`, the OMOP table
schemas `verify_omop_tables.py` runs.
