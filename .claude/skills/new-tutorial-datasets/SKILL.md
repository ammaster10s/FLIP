---
name: new-tutorial-datasets
description: Loaded by the new-tutorial router when a tutorial needs a new dataset under fl-tutorials/datasets/ or its data is access-controlled or private — dev-data layout, the dataset target, the OMOP chain for platform cohorts, and the data-access-tier rules behind fl-tutorials/specs/datasets.yaml.
user-invocable: false
---

# Datasets, dev data and access tiers

Reuse an existing dataset when the cohort fits — nothing here applies then beyond `DATA-01`
(the manifest's `dataset.target` resolves at the fl-tutorials root). Spec:
`fl-tutorials/specs/datasets.yaml`.

## Dev data: where the simulator reads from

Both harnesses run under `LOCAL_DEV` and read the shared, gitignored `fl-tutorials/data/`:

- Tabular: one CSV, `fl-tutorials/data/<dataset>/dataframe.csv`, with the columns `query.sql`
  would return on the platform (so the app's code is identical). Per-site splits are optional
  (`site1/`, `site2/` for the NVFLARE `SITE{N}_DATAFRAME` path); otherwise the app slices by
  `person_id` modulo.
- Imaging: `DEV_IMAGES_DIR` laid out the way imaging-api serves it — one directory per accession
  under `<dataset>/images/` or `accession-resources/`, containing what `flip.get_by_accession_number`
  would download (DICOM series, or NIfTI pairs `input_*.nii.gz` / `label_*.nii.gz` for the
  XNAT-converted path). Mirror the tree of the existing dataset closest in modality.

## Adding a dataset (`fl-tutorials/datasets/<dataset>/`)

The dataset dir is its own uv project (`pyproject.toml` declaring exactly what its scripts import —
the per-dataset test run is what catches an undeclared dependency), with:

1. A download / derive script (host-side; downloading here is allowed and expected — this tree is
   exempt from the offline-apps guard). Public sources only; large or private sets stay re-hosted
   on HF under `aicentreflip/` or behind a `make download-raw-*` the user runs (DATA-12).
2. Targets in `fl-tutorials/datasets/Makefile` named `download-<dataset>-data` (plus any
   `prepare-*` / `upload-*-labels` step), and **the same names appended to `DATASET_TARGETS` in
   `fl-tutorials/Makefile`** — the root forwards a fixed list, and
   `tests/test_fl_tutorials_make_targets.py` fails for any `make -C fl-tutorials <target>` a README
   quotes that does not resolve (DATA-01, DATA-02).
3. Tests under `fl-tutorials/tests/datasets/<dataset>/test_<script>.py`, and `<dataset>` appended to
   `DATASET_TEST_PROJECTS` in `fl-tutorials/Makefile` so they run in that project's env (DATA-04).
4. A section in `fl-tutorials/datasets/README.md` (DATA-03).

If the cohort must also exist **on the platform** (so `make e2e_smoke` and the dev trusts can run
it), the dataset needs the OMOP chain from `datasets/utils/` (#1092): a metadata table,
`omop_convert_<dataset>.py` building the OMOP tables through the shared contract
(`omop_schemas.py`, `omop_mappings.py`, a surrogate-key block in `omop_ids.py`),
`build-<dataset>-canonical`, `verify-<dataset>-omop-tables` through `verify_omop_tables.py
--project <name>`, and `seed-<dataset> KIT=` for a running dev trust (DATA-13). DICOMs regenerated
from open data are never published (only tables + `dicom_metadata.csv` go to
`aicentreflip/trust-data`); a new published cohort bumps `trust/.data_version`. That chain is a
project of its own (the prostate addition touched trust/omop-db, trust/orthanc, the Helm chart and
the compose seeding) — scope it explicitly with the user before starting, and read
`fl-tutorials/datasets/README.md` "OMOP mock-data generation" first.

## Data access tier: what the licence allows decides what the target may do

Ask what the source data's licence allows; it is the manifest's `dataset.tier`:

- **`public`** (MSD, Synthea, Hugging Face snapshots): a download script, as above.
- **`access_controlled`** (ADNI, UK Biobank, PI-CAI's clinical extras, anything behind a Data Use
  Agreement or an application): **nothing derived from it enters the repository** (DATA-05) — no
  rows, no per-subject tables, no per-site splits, no figure drawn from subject-level values, and no
  fixture built by thinning the real tables. Decide with the user whether readers are expected to
  hold the licence themselves (ADNI: an application most researchers can make) — then the dataset
  target is the **converter alone**, no synthetic stand-in, and the README's figures and reference
  numbers are *summary results* of a real run (edge frequencies, metrics), which such licences
  allow; the CPU tests use invented, source-shaped fixtures. Generate a synthetic stand-in (a
  seeded generator calibrated only to *published* summary statistics) only when the licence is out
  of most readers' reach. Either way the README documents the real-data path as **numbered steps a
  reader can follow end to end** (DATA-07): how to apply (where, what the application asks, how
  long review takes), the exact source tables to download (names, menu path, columns), a committed
  converter they run locally against that download (`make convert-<dataset>-cohort`, code only —
  it reads the source's public file and column names, writes the `query.sql` column contract to
  the gitignored data root — the target refuses a path inside the repository that git does not
  ignore (DATA-06) — and prints counts, never a row), and the run command with `DEV_DATAFRAME` /
  `SITE{N}_DATAFRAME` (or `SIM_DATA_ROOT` on Flower) pointing at the result. Read the licence itself
  before writing this: say which results it allows to be reported (ADNI: summary results only,
  with its acknowledgement and the download date) and whether it restricts AI tools (ADNI's clause
  4 does — the converter and simulator must run outside a coding assistant's view of the data)
  (DATA-10). The cohort is never seeded on the shared dev trusts; the licence holder loads their
  converted cohort into local trusts (DATA-09). No demo video — a recording would show derived
  values (DATA-08; waive COMMON-18 with that reason). Say in the README which numbers are from the
  synthetic set and which (if any) from a real run the author did under their own access.
- **`private`** (a trust's own cohort): simulator path on a synthetic stand-in as above; the real
  cohort is only ever reached through `query.sql` on the platform (DATA-11).

The same rule applies to the per-site partition: a modulo split of a real access-controlled table
may not be committed either, so the generator (or the converter, into the gitignored root) writes
the `site1/` / `site2/` splits.

## Precedents

`spleen` and `brain_mri` carry the full OMOP chain from a public MSD download; `cxr` the OMOP
conversion only; `synthea` the OMOP-only tabular path; `prostate` the multi-series imaging path
with its own prepare step; `arkplus` and `xrays_mini_300` are HF downloads; `ad_biomarkers` (with
the causal-discovery tutorial) is the converter-only, access-controlled precedent.

Spec: `fl-tutorials/specs/datasets.yaml` (DATA-01 to DATA-13).
