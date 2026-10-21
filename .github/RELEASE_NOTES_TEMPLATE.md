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

# :package: {{PROJECT}} {{VERSION}} Release Notes

## :sparkles: Highlights

- **Approved cohorts are frozen at approval** (#1066; issue #857). Each trust records the membership of an approved project once, and subsequent row-level requests can return only members of that frozen cohort. The store contains identifiers and the query of record, not clinical values. Existing approved projects need a one-time snapshot backfill after upgrading.
- **FLARE jobs can request GPUs per participating site** (#1423, #1424; issue #70). FLIP reads a researcher's request from the submission or `meta.json`; NVFLARE checks the available capacity at each site and queues jobs until the request can be met everywhere. Flower accepts and reports the request but does not schedule jobs by GPU.
- **Evaluation results appear in the hub** (#1527; issue #1526). FLARE evaluation metrics are now sent to the hub alongside Flower metrics, while supplementary evaluator output remains available in the downloaded results.
- **Native XNAT imaging workflows** (#1475). Trust administrators can use XNAT's native archive and user operations, with safer import handling, timeouts, and recovery for existing imaging data.

## :warning: Breaking Changes

- **Trusts now serve row-level cohort data only after the approved membership has been frozen** (#1066). Existing approved projects have no snapshot until backfilled; training and imaging retrieval for those projects will fail closed in the meantime. Pause approvals and training during the upgrade, move the hub and all participating sites in one Deployment-Mode window, then backfill approved projects before resuming work.
- **FLARE jobs now use the per-site resource contract** (#1424). Invalid or unsupported `meta.json` keys and per-site resource blocks are rejected. FLARE site capacity is read from the deployed trust kit; set `NUM_AVAILABLE_GPUS` to the GPUs available to the FL client before relying on GPU scheduling.

## :arrows_counterclockwise: Site upgrade

<!-- The prompt to trust operators (FLIP#1204). Sites upgrade on their own schedule and to the
     release their hub runs; this section is how they learn what this release asks of them. -->

- **Required:** yes. Upgrade the hub and every site participating in a project before resuming approvals, imaging pulls, or training. An upgraded site refuses row-level data for projects without a frozen snapshot; an old site cannot process the hub's new snapshot task.
- **Ordering:** one coordinated Deployment-Mode window. Pause project approvals and FL jobs; upgrade the hub first, then every participating site; backfill snapshots for existing approved projects with `make -C flip-api backfill_cohort_snapshots`; check the project cohort-snapshot status before resuming work.
- **Kubernetes trusts:** required as part of the same window; deploy the matching release to every participating trust.
- **Refreshed kit needed:** no. Kits no longer carry the hub's registry, and a stale registry line is ignored (#1483). The new `FL_EDGE_PORT` defaults to `FL_SERVER_PORT` (#1507). Confirm `NUM_AVAILABLE_GPUS` on FLARE kits if you enable GPU-aware scheduling.
- **Take the images with the compose** (#1537). The production trust compose no longer grants the capabilities that let pre-hardening root images start. Upgrade with `upgrade-onprem-trust`, which moves images and compose together; never run this compose on an older image pin. A host that ran the root fl-client needs the one-time `chown` in `fl-services/nvflare/README.md` (*Upgrading an existing environment*).
- **Trust data `20261019`** (#1562) changes only the mock tutorial data. A site upgrade does not re-seed. Demo and mock trusts re-seed on their next `make up`.
- **Operator command**, on the trust host, from your FLIP checkout:
  ```bash
  git fetch --tags origin && git checkout {{TAG}}        # the compose files and the verb come from the checkout, not the images
  sudo -E make upgrade-onprem-trust KIT=<slot>           # defaults to the release the hub now reports
  ```
  Kubernetes: `make -C trust/deploy/helm upgrade-trust-k8s KIT=<CODE> PROD=<env> TAG={{TAG}}`; EC2: `make -C deploy/providers/AWS upgrade-trust-ec2 KIT=<CODE> PROD=<env> TAG={{TAG}}`, both from a checkout at {{TAG}}. Runbook: *docs → System administrators → Upgrading a site*.

## :seedling: New Features

- Approved-cohort snapshot status, retry, and backfill support in the hub; row-level trust APIs now enforce the frozen membership and disclosure threshold (#1066).
- Per-job GPU requests for FLARE, using researcher declarations, submission overrides, site resource availability, and scheduler feedback. Flower reports GPU requests as unenforced (#1423, #1424).
- FLARE evaluation metrics are forwarded to the hub, including per-model labels and finite numeric values; supplementary results remain in `evaluation_results.json` (#1527).
- XNAT's native archive operations, safer DICOM import and recovery tooling, and improved timeout handling (#1475, #1512, #1522, #1539, #1566).
- A Playwright-based demo recorder, with hub and trust approval steps and reusable UI captions (#1505, #1566).
- A local stack needs no AWS: the x-ray tutorial and `make e2e_smoke` run without the licensed core vocabulary (#1499, #1560). Also GPU resource visibility for Helm FLARE clients, Helm trust-data pinning, and a documentation overhaul (#1510, #1564, #1550).

## :bug: Bug Fixes

- Cohort queries on a local stack work without a separately loaded core vocabulary (#1499).
- XNAT prearchive `ERROR` sessions are reported as failed, rather than successful (#1512).
- Helm 4 upgrades recreate the XNAT workload before applying changes, avoiding a stuck rollout on its single-writer volume (#1525).
- An FL job whose server-side process dies without reporting is failed by a hub watchdog and its net freed, instead of staying RUNNING (#1497). Jobs waiting for GPUs report the scheduler's verdict instead of being demoted (#1423).
- The cohort sex chart reads the standard OMOP Gender concept, and the tutorial data now uses Gender concepts (#1562). Age bands sort naturally (#1565). The login email error no longer flashes while typing, and Stop Training is hidden once training ends (#1530). Large uploads to the dev object store no longer fail (#1536).

## :white_check_mark: Release checks

<!-- These checks are release evidence and must be run for v0.13.0. Do not carry forward results
     from an earlier release. Record the host, date and outcome before merging the release PR. -->

Run at `a60570cec` on an RTX 5090 workstation, 20 October 2026. The commits after it change only these notes.

Tutorial suite, on a GPU host:

- [x] FLARE — `make -C fl-tutorials run-all-tutorials`: 8/8 passed in 811 s (arkplus_fine_tuning,
  xray_classification, 3d_spleen_segmentation_evaluation (mean Dice 0.934), arkplus_baseline_classification_evaluation,
  arkplus_multimodel_classification_evaluation, 3d_spleen_segmentation, latent_diffusion_model, ehr_risk_prediction)
- [x] Flower — `make -C fl-tutorials run-all-tutorials FL_BACKEND=flower`: 5/5 passed in 275 s (3d_prostate_segmentation,
  3d_spleen_segmentation, 3d_spleen_segmentation_evaluation, ehr_risk_prediction, xray_classification)
- [x] Host, date, and results recorded: above

Full-platform smoke test, against a running deployment:

- [x] FLARE — `make e2e_smoke`: passed in 821 s, both trusts pulled 300/300 images, `RESULTS_UPLOADED`
- [x] Flower — `make e2e_smoke FL_BACKEND=flower`: passed in 605 s on the same project, `RESULTS_UPLOADED`
- [x] Host, date, deployment, and results recorded: a fresh isolated instance (`FLIP_INSTANCE=rel0130`, its own ports
  and env file, GSTT + KCH trusts) brought up from empty volumes, with every repo-built image built from this commit
  at `:rel0130` (hub and trust APIs, flip-ui, orthanc, omop-db, XNAT, both FL backends); none pulled from `:stag`/`:dev`

Local checks:

- [x] `make unit_test`: all suites passed (flip-api 2220, flip-ui 1600, data-access-api 464, imaging-api 804,
  omop-db 115, trust-api 174, xnat 511). The xnat count is from a clean checkout at the same commit: in the gate
  checkout, two container-lookup tests picked up the instance's `FLIP_INSTANCE` and failed (fixed in #1606)
- [x] `make integration_test`: flip-api 237, data-access-api 14, trust-api 8 passed

## :file_folder: PRs merged in this release

<!-- auto-populated by the release workflow -->

## :star: Acknowledgements

A big thank you to the following contributors for their work on this release:

<!-- auto-populated by the release workflow -->
