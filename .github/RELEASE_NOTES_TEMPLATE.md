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
- **Refreshed kit needed:** no. The Hub-shared block is unchanged. Confirm `NUM_AVAILABLE_GPUS` on FLARE kits if enabling GPU-aware scheduling.
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
- A Playwright-based demo recorder, with hub and trust approval steps and reusable UI captions (#1504, #1566).
- A no-AWS local development workflow, GPU resource visibility, Helm trust-data pinning, and a broader tutorial and documentation refresh (#1560, #1510, #1564, #1550).

## :bug: Bug Fixes

- Cohort queries on a local stack work without a separately loaded core vocabulary (#1499).
- XNAT prearchive `ERROR` sessions are reported as failed, rather than successful (#1512).
- Helm 4 upgrades recreate the XNAT workload before applying changes, avoiding a stuck rollout on its single-writer volume (#1525).
- Training stops cleanly after invalid user input, stale FL jobs are recovered, and queued work reports site scheduling failures (#1497, #1529, #1390).
- UI cohort-chart ordering, demo recording, model upload validation, and development object-store error handling are improved (#1565, #1504, #1538, #1534).

## :white_check_mark: Release checks

<!-- These checks are release evidence and must be run for v0.13.0. Do not carry forward results
     from an earlier release. Record the host, date and outcome before merging the release PR. -->

Tutorial suite, on a GPU host:

- [ ] FLARE — `make -C fl-tutorials run-all-tutorials`
- [ ] Flower — `make -C fl-tutorials run-all-tutorials FL_BACKEND=flower`
- [ ] Host, date, and results recorded:

Full-platform smoke test, against a running deployment:

- [ ] FLARE — `make e2e_smoke`
- [ ] Flower — `make e2e_smoke FL_BACKEND=flower`
- [ ] Host, date, deployment, and results recorded:

Local checks:

- [ ] `make unit_test`
- [ ] `make integration_test`

## :file_folder: PRs merged in this release

<!-- auto-populated by the release workflow -->

## :star: Acknowledgements

A big thank you to the following contributors for their work on this release:

<!-- auto-populated by the release workflow -->
