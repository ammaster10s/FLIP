# Every hand-maintained list a tutorial touches

Derived from the tree, nothing to edit: tutorial discovery on both backends, the parity /
min-clients / import-path / offline-apps guards, ruff, and — since the specs — which rules apply
(the manifest selects them). Hand-maintained — check each one; the rule that checks it is in
brackets, SHOULD rules print as ⚠️ so a missing mention is visible, not fatal:

| Where | When |
|-------|------|
| `tutorial.yaml` at the tutorial root | Every tutorial (COMMON-01; copy a neighbour's, `fl-tutorials/specs/README.md` has the schema) |
| `fl-tutorials/flower/sim-tutorial.sh` `case` block (+ the `RUN_CONFIG` line for evaluation) | Every Flower tutorial (FLWR-10, EVAL-07; mandatory, tested) |
| `fl-tutorials/Makefile` `DATASET_TARGETS`, `DATASET_TEST_PROJECTS` | New dataset target / dataset test project (DATA-01, DATA-04) |
| `fl-tutorials/datasets/Makefile` + `datasets/README.md` | New dataset (`new-tutorial-datasets`) |
| `fl-tutorials/tests/tutorial_apps.py` `DICOM_APPS` | App reads 2-D DICOM through MONAI `LoadImaged` (IMG-04) |
| `scripts/check_tutorial_sync.sh` `PAIRS` + `.github/workflows/fl-apps-check-tutorial-sync.yml` `paths:` | Files shared byte-for-byte between tutorials; every twin pair's `query.sql` (COMMON-16, COMMON-28) |
| `fl-tutorials/AGENTS.md` path table; `fl-tutorials/README.md` backend table and dataset-download sentence | Every tutorial (COMMON-23, COMMON-24) |
| `AGENTS.md` (root) `fl-tutorials/` line in the repo-structure block | Every tutorial (COMMON-25; it enumerates them) |
| `docs/source/components/component-fl-nets.rst` "The NVFLARE tutorials" list (name, link, job type) | Every NVFLARE tutorial |
| `docs/source/working-with-flip-apps/create-flip-app-from-{flare,flower}.rst` worked-example bullets; `package-model-as-map.rst` transforms table | When the tutorial is a better worked example / ships `transforms.py` + `export/metadata.json` |
| `docs/source/components/component-omop-database.rst` "Sample cohort queries" | New `query.sql` worth showing |
| `flip-api/Makefile` `e2e_smoke_<name>` target (+ `flip-api/AGENTS.md`, root `AGENTS.md` smoke section); `flip-api/tests/e2e_smoke.py` `TUTORIALS` label map | When the tutorial should be drivable end to end against the dev stack — needs its cohort seeded on the trusts; the manifest's `platform.e2e_target` (COMMON-17, TAB-03, IMG-06) |
| `flip-api/tests/demo_video.py` `APPS` profile (+ `flip-ui/test/cypress/demo/README.md` example when enrichment flags are needed) | Every tutorial that gets a demo video; the manifest's `platform.demo_profile` (COMMON-18, TAB-04, IMG-09); same seeded-cohort prerequisite as e2e |
| `CONTRIBUTING.md` pre-release checklist | Only if the tutorial needs an extra input before `run-all-tutorials` (a checkpoint, `NUM_CASES`, a prepare step) |
| `.secrets.baseline` | If detect-secrets flags a placeholder (e.g. a UUID or URL) in the new files |
