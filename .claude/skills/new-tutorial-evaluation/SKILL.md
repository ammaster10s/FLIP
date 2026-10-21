---
name: new-tutorial-evaluation
description: Loaded by the new-tutorial router for an evaluation tutorial (no training; an uploaded checkpoint is evaluated at every site) — evaluator.py / the evaluation template, checkpoint staging, the simulator RUN_CONFIG, query reuse and the demo-recorder caveat behind fl-tutorials/specs/loop-evaluation.yaml.
user-invocable: false
---

# Evaluation tutorials

An evaluation job submits a checkpoint and trains nothing: every site loads it, runs inference
over its cohort and reports metrics; the server aggregates the metrics, not the weights. Manifest:
`loop: evaluation`, `job_type: evaluation` (EVAL-01), `weights_target` naming the staging target
(EVAL-06), `query_from` naming the training tutorial whose cohort it evaluates (EVAL-08,
COMMON-29/30). Spec: `fl-tutorials/specs/loop-evaluation.yaml`.

## Per backend

**NVFLARE.** `FlipEvalRecipe(eval_script="evaluator.py", …)`; required files `evaluator.py`,
`config.json`, `models.py`. `evaluator.py` is the same Client-API loop as a trainer (EVAL-02) but
only answers `is_evaluate()` / `is_submit_model()`. The checkpoint is fetched by the Makefile's
`download-checkpoints` (spleen) or `prepare-checkpoint` (Ark+, which converts an upstream pickle
host-side first) into `app_files/`, and `.gitignore` keeps `*.pt` out. The Ark+ multimodel
evaluation shows several checkpoints in one job with per-model metrics on the hub.

**Flower.** The `fl-apps/flower/evaluation` template (`EvaluationStrategy`); `project.name =
"evaluation-app"`; `num-server-rounds = 1` (EVAL-03); `checkpoint = "model.pt"` relative to
`flip-job-dir`, which fl-api sets to the uploaded bundle's dir at submit time (EVAL-04); no `dp-*`
and no best-model keys (EVAL-05). The tutorial carries an `.env.app` with `MODEL_CHECKPOINT_URL`
(EVAL-09) and a Makefile `download-checkpoints` target that curls it into `app/`. The simulator has
no submit step, so `sim-tutorial.sh` supplies `RUN_CONFIG="flip-job-dir=… checkpoint=model.pt"`
pointing at `fl-tutorials/data/model_checkpoints/` (EVAL-07) — copy the
`3d_spleen_segmentation_evaluation` branch. No `query.sql` of its own: the e2e target points
`QUERY_FILE` at the training tutorial's (EVAL-08).

## Traps

- **The demo recorder assumes training.** Segments 4–5 do create model → initiate training →
  live metrics → download; an evaluation job shows none of that, so recording one today produces
  a misleading video. Leave `platform.demo_profile` null and waive COMMON-18 with that reason
  (EVAL-10) until an evaluation variant of the segments exists (#1444).
- **The checkpoint is an uploaded file, never a run-time download** (DL-01, DL-07): the Trust
  inspects what runs.
- **What the metrics mean.** The README says plainly that nothing is trained and what each
  reported metric is per site (EVAL-11), and names the training tutorial whose cohort and
  checkpoint it evaluates (EVAL-12). The task figure can show the model's prediction beside the
  label; "Expected performance" is the per-site metric table the shipped checkpoint reaches.

## Nearest tutorials to copy

| Shape | NVFLARE | Flower |
|-------|---------|--------|
| 3-D segmentation checkpoint | `image_evaluation/3d_spleen_segmentation_evaluation` | `3d_spleen_segmentation_evaluation` |
| 2-D classification, one / several checkpoints | `image_evaluation/arkplus_baseline_classification_evaluation`, `…/arkplus_multimodel_classification_evaluation` | — |

Spec: `fl-tutorials/specs/loop-evaluation.yaml` (EVAL-01 to EVAL-12).
