---
name: new-tutorial-tabular
description: Loaded by the new-tutorial router for a tabular / OMOP-only tutorial (has_imaging off, CPU, person_id cohorts, one CSV partitioned per site) — the why behind fl-tutorials/specs/data-tabular.yaml.
user-invocable: false
---

# Tabular / OMOP-only tutorials

A tabular tutorial reads nothing but the cohort dataframe: `flip.get_dataframe(project_id,
query)` returns the rows `query.sql` selects from the trust's OMOP CDM, and the app never calls
`get_by_accession_number` (TAB-05). The platform project is created with **imaging off**
(`has_imaging=false`, FLIP#1071; TAB-02): left on, the hub dispatches `create_imaging`, each trust
queues pulls that can never succeed, and the run dies at the image-pull wait. Everything
downstream follows from that switch. Spec: `fl-tutorials/specs/data-tabular.yaml`.

## Rules and traps

- **`person_id` is mandatory in `query.sql`** (TAB-01). The trust's disclosure floor
  (`COHORT_QUERY_THRESHOLD`) counts distinct subjects, a cohort exposing neither `person_id` nor
  `accession_id` is refused at approval, and the per-site partition keys on it.
- **One CSV, sliced per site.** Under the simulator every site sees the same
  `fl-tutorials/data/<dataset>/dataframe.csv` (the columns `query.sql` would return, so the app
  code is identical on the platform). NVFLARE: `.env.app` sets `DEV_DATAFRAME` (and optionally
  `SITE{N}_DATAFRAME` for pre-split files) and the trainer slices by `person_id` modulo
  `DEV_NUM_PARTITIONS`; Flower: `partition_cohort(df, context)` (TAB-08). No `IMAGES_DIR` anywhere
  (TAB-07); the `sim-tutorial.sh` case sets `DEV_DATAFRAME` only.
- **CPU.** The simulator runs in minutes on CPU; the manifest says `simulator: {device: cpu}`
  (TAB-06), so CI-adjacent checks and reviewers can run it.
- **e2e and demo wiring.** The e2e target pins `TARGET_ARGS := --no-imaging` (`e2e_smoke_ehr` is the
  pattern; TAB-03) and the demo profile sets `"has_imaging": False` so the XNAT/OHIF segment is
  skipped (TAB-04). Both need the cohort loaded into the dev trusts' OMOP databases: public OMOP-only
  data has a load target (`make -C trust load-synthea-ehr`); an access-controlled cohort is loaded
  only by its licence holder into **local** trusts (`load-adni-cohort`), never seeded on the shared
  ones.
- **The figure.** There are no images to show: draw the feature set and the label's prevalence
  from the dev CSV (TAB-10), with the usual committed script under `docs/`.
- **Feature engineering is shared.** When the tutorial exists on both backends, the feature
  engineering, model factory and `query.sql` are byte-identical copies pinned in
  `scripts/check_tutorial_sync.sh` (the EHR pair is the precedent), so both backends train the same
  model on the same columns.
- **README.** Say the project is created with imaging off and name the `--no-imaging` e2e target
  (TAB-09); the EHR README's Data section (local CSV vs on the platform / OMOP) is the template.

## Nearest tutorials to copy

| Shape | NVFLARE | Flower |
|-------|---------|--------|
| Tabular deep learning (MLP, FedAvg) | `tabular_classification/ehr_risk_prediction` | `ehr_risk_prediction` (take identity from `client_identity`, not `SUPERNODE_NAME`) |
| Tabular statistical (no training) | `tabular_causal_discovery/biomarker_causal_discovery` once it lands | `biomarker_causal_discovery` once it lands — see `new-tutorial-statistical` |

Spec: `fl-tutorials/specs/data-tabular.yaml` (TAB-01 to TAB-10).
