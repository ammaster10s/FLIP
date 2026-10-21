---
name: new-tutorial-deep-learning
description: Loaded by the new-tutorial router for a deep-learning tutorial (a torch / MONAI module trained or evaluated by FedAvg) — offline weights, weights_only, best-model selection, DP, the reference training curve; the why behind fl-tutorials/specs/model-deep-learning.yaml.
user-invocable: false
---

# Deep-learning tutorials

The model is a torch / MONAI module built by a zero-argument `get_model()` (DL-03): the server
seeds round 0 with it, FedAvg averages its arrays by site size, and the best round is picked by
the metric the config names. Spec: `fl-tutorials/specs/model-deep-learning.yaml`, on top of the
backend spec.

## Weights never arrive at run time

Nothing under `app/` or `app_files/` may download (#1206; DL-01): no `pretrained=True`,
torchvision `weights=`, `torch.hub.load`, `from_pretrained("org/x")`, `load_state_dict_from_url`,
MONAI bundle download, and no `PerceptualLoss` / `LPIPS` unless the module first stages a
torch.hub dir. On a platform-managed estate the FL server has no internet route, nor does a trust
host behind an NHS firewall (the server-side job process hangs; FLARE clients die with `cannot
sync with server Runner`, Flower never issues a round), and a run-time fetch bypasses the scanned
upload — the file a Trust can inspect is no longer the file that runs. Weights ship as uploaded
files (`.safetensors` preferred); a tutorial that needs one stages it **host-side** with a
Makefile target the manifest names as `weights_target` (DL-07): `make weights` through the shared,
hash-checked `make -C fl-tutorials download-weights ARCH=<arch>` (checkpoints listed in
`fl-tutorials/datasets/weights/fetch_weights.py`), `download-checkpoints` for an evaluation
checkpoint, `prepare-checkpoint` for a converted foundation-model checkpoint.

Every `torch.load` passes `weights_only=True` (#1245 / #1249; DL-02): a checkpoint that unpickles
arbitrary objects is code execution beside patient data. Raw upstream checkpoints that need full
unpickling are converted host-side under the tutorial's `process_tools/`, outside the walked app
dirs (DL-10). `fl-tutorials/tests/test_offline_apps.py` is the AST guard for both rules — a lint,
not a sandbox; the spec's regexes are the fast approximation.

## Selection, privacy, metrics

- **Best-model keys.** NVFLARE: `BEST_MODEL_METRIC` / `BEST_MODEL_METRIC_MINIMIZE` in
  `config.json`, passed by `job.py` to the recipe (DL-04). Flower: `best-model-metric` /
  `best-model-metric-minimize` in the pyproject config, a key the ClientApp's evaluate reply
  reports (FLWR-22). Without them the platform keeps the last round.
- **Differential privacy on.** Flower: `dp-enabled = true` and the train handler under
  `flip_local_dp_mod` (DL-05, DL-06; `flip.flower.privacy.LocalDpConfig` reads the five `dp-*`
  keys). NVFLARE: the recipe's percentile privacy filter is on by default — the trainer sends the
  full state dict and the filter clips it.
- **Metrics.** NVFLARE trainers publish through `SummaryWriter` (TensorBoard events in the
  simulator workspace); Flower replies carry a `MetricRecord` with `<label>[@<x_label>][.x_<N>]`
  keys and the template server writes the cross-validation JSON. Those two artefacts are what the
  reference curve is drawn from.

## What the README shows

- The **input → output figure** per the router's `readme-shape.md` (DL-08).
- A **reference training curve** from a simulator run with the shipped config — best-model
  metric and loss per global round, per site and aggregated — from the TensorBoard events / CV
  JSON through a committed `docs/make_training_curve.py`; the first one written should be generic
  enough to move to `fl-tutorials/datasets/` or `scripts/` and be shared.
- The **numbers in prose** (DL-09): the metric range, rounds to plateau, which config knobs it
  depends on, the hardware and wall-clock, and the failure signatures a reader might mistake for
  normal (NaN metrics on class imbalance → ~300 samples per site; a metric stuck at round 0's
  value; a Flower site that trains on the whole CSV because identity was not partitioned).
- `## References`: the method paper with BibTeX, the dataset and licence, the checkpoint's source
  and licence, and what differs from the paper (COMMON-21).

## Nearest tutorials to copy

By data shape, see `new-tutorial-imaging` / `new-tutorial-tabular`; by loop, `new-tutorial-evaluation`
/ `new-tutorial-training-variants`. Plain FedAvg precedents: `xray_classification` (DenseNet121,
2-D), `3d_spleen_segmentation` (UNet, 3-D), `ehr_risk_prediction` (MLP, tabular),
`3d_prostate_segmentation` (nnU-Net-planned DynUNet, Flower).

Spec: `fl-tutorials/specs/model-deep-learning.yaml` (DL-01 to DL-10).
