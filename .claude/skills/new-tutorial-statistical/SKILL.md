---
name: new-tutorial-statistical
description: Loaded by the new-tutorial router for a statistical tutorial (no trainable parameters; sufficient statistics or votes summed through FedAvg, e.g. federated causal discovery) — the round protocol, privacy-filter fit, floors and refusals behind fl-tutorials/specs/model-statistical.yaml.
user-invocable: false
---

# Statistical tutorials: FedAvg as a summation channel

Nothing is trained. The "model" is a module of **buffers, no parameters** (STAT-18) that carries
what the method needs pooled across sites, and FedAvg's size-weighted mean is used as the
arithmetic: when every site sends its statistic weighted by its row count `n`, the aggregate is
exactly the pooled statistic. The precedent is `biomarker_causal_discovery` — bootstrapped FCI
over pooled Fisher-z sufficient statistics (FedC²SL-style), or FedPC-style layer voting — on both
backends, with `federated_fci.py` as the shared core. Manifest: `model: statistical`,
`loop: statistics_fedavg` (STAT-01). Spec: `fl-tutorials/specs/model-statistical.yaml`.

## The protocol

- **Round 1: statistics.** Each site sends one mean vector and one second-moment matrix (or its
  votes), with the FedAvg weight set to its row count — NVFLARE `meta={"NUM_STEPS_CURRENT_ROUND":
  n}` (STAT-08), Flower `num-examples = n` (STAT-09). The total `N` is recovered on the next round
  from the aggregate (the causal tutorial squares and sums `site_counts` slots).
- **Round 2: the result.** Every site computes the same answer from the pooled statistic (FCI on
  the pooled correlation with a parametric bootstrap), so all sites return identical arrays and the
  mean is exact; the statistics are zeroed before the result goes back. **One round is refused**
  (STAT-02, STAT-03): with `GLOBAL_ROUNDS=1` the per-site statistics themselves would be the
  published result. `config.json` asks for ≥ 2 rounds; a voting mode needs `L + 2`.
- **Best-model selection off** — "best" has no meaning for a state: no `BEST_MODEL_METRIC` in the
  NVFLARE config (STAT-06), `best-model-metric = ""` on Flower (STAT-07).
- **Cohort fetched once per run** (STAT-19): Flower caches it in `context.state`, NVFLARE loads it
  before the round loop.

## Privacy: what leaves a site, and the filters it passes through

- **DP off, and say why** (STAT-04, STAT-05): clipping and noising pooled second moments or 0/1
  votes is not a meaningful mechanism for them and breaks the arithmetic. The README's privacy
  section states what each site sends, what the platform's filters do to it, and why DP is off.
- **Fit the NVFLARE percentile privacy filter** rather than fight it: shape the payload (an
  `ENCODING_SCALE`, a zero padding buffer, scaled columns) so the filter passes it untouched, and
  **assert** that it will (`assert_within_filter_bounds`, STAT-10) instead of letting a clipped
  value through silently; honour a stricter `gamma` from the site policy.
- **Floors.** Re-read the trust's own disclosure floor (`COHORT_QUERY_THRESHOLD`, the kit value the
  data-access gate uses) on the FL client (STAT-11); a hard minimum site size that config can only
  raise (`HARD_MIN_SITE_ROWS`, STAT-12); a small-cell floor on discrete levels (`MIN_CELL_COUNT`,
  STAT-13).
- **Refusals name neither the count nor the column** (STAT-14): a refusal that says "17 rows" or
  "apoe4 has a cell of 3" is itself a disclosure.
- **Anything that publishes more than the pooled statistic** — per-layer votes, per-site edges,
  per-bootstrap outputs — runs under `LOCAL_DEV` only (`layer_voting_allowed`, STAT-15); the
  deployed default is the one-statistic-per-site mode.

## What the README shows

- The **flow diagram** (Mermaid) of both modes: what each site sends per round, how the server's
  mean becomes the pooled statistic, where the result is computed.
- **Expected performance is an agreement table, not a curve** (STAT-17): centralised vs pooled vs
  voting, edge frequencies over bootstraps, with the failure signatures (a one-round run, a site
  under the floor, a refused cell).
- **`## References` is mandatory** (STAT-16): the federated method built on (and where the tutorial
  departs from it — FLIP's FedAvg-only plumbing, the filters, the cohort shape), the centralised
  method, the data.
- **No demo video when the data is access-controlled**: a recording would show derived values
  (DATA-08); waive COMMON-18 with that reason. Dataset-tier rules: `new-tutorial-datasets`.

## Design note first

Before code, search for existing work that federates the method (router §1.7) and write down
what each client sends, how the server combines it, and which assumptions that adds (IID,
discrete variables, equal site sizes, a trusted server). A method that cannot be expressed as a
size-weighted mean of client arrays does not fit the fixed Flower template `server_app.py` /
`strategy.py` or the NVFLARE recipes — say so and stop rather than edit the templates.

Spec: `fl-tutorials/specs/model-statistical.yaml` (STAT-01 to STAT-19).
