---
name: new-tutorial-training-variants
description: Loaded by the new-tutorial router for a training loop that is not plain FedAvg of a fresh model — fine-tuning a shipped checkpoint with partial aggregation, the FedOpt recipe, or a two-stage (autoencoder then diffusion) job — the why behind fl-tutorials/specs/loop-training-variants.yaml.
user-invocable: false
---

# Training variants

Plain FedAvg of a freshly initialised model needs nothing beyond the backend skill. Three loops
in the catalogue differ, and the manifest's `loop` says which. Spec:
`fl-tutorials/specs/loop-training-variants.yaml`.

## `fine_tune` — a shipped checkpoint, part of the model frozen or aggregated only

Precedent: `arkplus_fine_tuning` (NVFLARE). The Ark+ Swin-Large backbone is frozen and only the
new heads train; two `config.json` keys carry that to the recipe: `SERVER_CHECKPOINT` (the file
the server seeds round 0 from, TRV-01) and `AGGREGATE_ONLY_REGEX` (`"omni_heads"` — only matching
arrays are averaged, so the frozen backbone is never touched by aggregation or the privacy
filter, TRV-02). The checkpoint is prepared host-side by `make prepare-checkpoint` (a converted
upstream pickle, see `process_tools/`) and named as `weights_target` (TRV-03); it is an uploaded
file, never fetched at run time. `job_type` stays `standard`. The README carries a Mermaid block
showing what is frozen, what is aggregated and what trains (TRV-09, TRV-10). On Flower there is no
precedent yet: the template strategy averages every array, so partial aggregation needs the array
split done in the ClientApp (send only the trained arrays) — a design note before code.

## `fed_opt` — the FedOpt recipe

`FlipFedOptRecipe` (`fl-apps/nvflare/fed_opt`) adds a server-side optimiser
(`optimizer_args`, `lr_scheduler_args`, `device`); required files are the standard set;
`job_type: fed_opt` (TRV-07, TRV-08). **No tutorial uses it yet** — a new one copies
`ehr_risk_prediction` or `xray_classification` and swaps the recipe class in `job.py`; say in the
README what the server optimiser changes against FedAvg and show it in the reference curve.

## `two_stage` — autoencoder, then diffusion model, in one job

Precedent: `latent_diffusion_model` (NVFLARE only, TRV-04): `FlipDiffusionRecipe` with
`num_rounds_ae` + `num_rounds_dm` (TRV-06), `job_type: diffusion_model` (TRV-05), required files
`trainer.py`, `validator.py`, `config.json`, `models.py`. The perceptual loss needs SqueezeNet
weights staged by `make weights` (shared `download-weights`, hash-checked) into `app_files/`
(TRV-03) — `PerceptualLoss` without a staged hub dir is a run-time download and the offline guard
refuses it (`test_ldm_offline_backbone.py` pins the staging). The README's Mermaid block shows the
two stages and which rounds belong to each (TRV-09). It trains on the spleen volumes and reuses
that cohort (`query_from: 3d_spleen_segmentation`).

## Common to all three

- Say in the README what differs from plain FedAvg and why — the generic job-type figure lives in
  the docs (`docs/source/assets/fl/job_types.jpg`), so a Mermaid block for *this* loop is enough.
- The reference curve shows the stage or the trained part only; a frozen backbone has no curve.
- Registration is the same as any tutorial; the docs catalogue line names the job type.

Spec: `fl-tutorials/specs/loop-training-variants.yaml` (TRV-01 to TRV-10).
