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

- **A trust can decide its own projects** (#1266, #1298) — hub approval stays the default: the hub administrator approves or declines for a trust until that trust has a **Trust Admin**, and from then on only its Trust Admins decide for it. Appointing a trust's first Trust Admin hands its decisions to the site and removing the last hands them back; there is no setting to keep in step. A Trust Admin is assigned from the Users tab with the trust they administer, and works from a new *My Trust* page: the requests awaiting their decision (with their own trust's cohort count), the projects already decided, and their trust's connection status.
- **Each trust's decision is recorded, and can be a decline** (#1321, #1266) — an approver can decline a trust as well as approve it, and every decision keeps who made it, when, and whether the hub or the site decided. The project page shows each trust's decision, and a trust with a Trust Admin is read-only there for the hub.
- **XNAT trusts can point at a real Trust PACS** (#1234) — the DICOM SCP gets a Service of its own, separate from the web UI, with a fixed node port or a load balancer for a PACS outside the cluster, and the chart refuses to render a real-PACS install that would expose the console in order to reach it.
- **The published tutorials and the platform path become release gates** (#1306) — neither can run in CI (no hosted runner has a GPU, and the smoke test needs a full stack), so the GPU tutorial suite on both backends and `make e2e_smoke` are ticked in the *Release checks* section of this file and in the pre-release checklist.

## :warning: Breaking Changes

- **Approval is no longer a single call** (#1266). A project used to be approved once, for the trusts named in that call, and a trust left out stayed out. Now each trust decides on its own: the project is approved at the first trust's approval, and the others may approve or decline later. A trust that approves late is linked to the project's existing models and takes part from their next run, and imaging starts at a trust only once that trust has approved. A project every trust declines stays staged. Who decides is unchanged on a deployment with no Trust Admins: the hub administrator, as before.
- **Trusts left pending on already-approved projects are closed at upgrade** (#1266). Such a trust used to be simply left out; under the new rule it could still approve and join a long-settled project. The migration marks it declined with no decider or date, and the UI shows it as *Not approved · No decision recorded*. The migration's downgrade reopens exactly those trusts.
- **DICOM exposure moves to its own Service on Helm trusts** (#1234). `xnat-web.service` used to be what exposed DICOM; it is now held at `ClusterIP`, so a DICOM exposure can never publish the Tomcat console with it. An install that set it to `NodePort` to reach a real PACS must move to `dicomService.type` (with `dicomNodePort`) or `LoadBalancer`, and reach the console with `kubectl port-forward`. The chart fails that render (`validatePacsReachable`) rather than reverting the exposure quietly.

## :arrows_counterclockwise: Site upgrade

<!-- The prompt to trust operators (FLIP#1204). Sites upgrade on their own schedule and to the
     release their hub runs; this section is how they learn what this release asks of them. -->

<!-- Fill the first three lines in for EVERY release; they are not boilerplate. "Ordering" is where a
     flag-day is announced: a payload-cipher change or an FL-framework bump means hub AND sites in one
     Deployment-Mode window, and a site left behind fails every task until it moves. -->

- **Required:** no, if you are on v0.7.0 or later — nothing in this release changes the hub↔site payload contract. **Recommended for Kubernetes trusts**, which can now reach a real PACS (#1234) and whose seed hook fails on earlier releases (#1310). **Yes, and as a flag day, if you are on v0.6.x or earlier**: you cross v0.7.0's AES-256-GCM change on the way here, and that has no CBC fallback.
- **Ordering:** hub first, sites at their own pace — *unless* you are coming from v0.6.x, in which case hub and sites move together in one Deployment-Mode window and a site left behind answers every task `Invalid payload: failed authentication`.
- **Refreshed kit needed:** no — the Hub-shared block is unchanged. If you percent-encoded `DATA_ACCESS_POSTGRES_PASSWORD` by hand, give it raw now: data-access-api escapes it itself (#1310), so an encoded value would be encoded twice. (If the hub's AES key or FL kit date changed with your hub deploy, re-sync: `make sync-trust-kit KIT=<CODE> PROD=<env>` → `make -C deploy/providers/AWS package-onprem-trust-kit KIT=<CODE>`.)
- **Operator command**, on the trust host, from your FLIP checkout:
  ```bash
  git fetch --tags origin && git checkout {{TAG}}        # the compose files and the verb come from the checkout, not the images
  sudo -E make upgrade-onprem-trust KIT=<slot>           # defaults to the release the hub runs; TAG={{TAG}} pins it before the hub moves
  ```
  Kubernetes: `make -C trust/deploy/helm upgrade-trust-k8s KIT=<CODE> PROD=<env> TAG={{TAG}}`; EC2: `make -C deploy/providers/AWS upgrade-trust-ec2 KIT=<CODE> PROD=<env> TAG={{TAG}}` — both from a checkout at {{TAG}}. Runbook: *docs → System administrators → Upgrading a site*. Sites on v0.7.0 or earlier do not have the command until they check out the tag.

## :seedling: New Features

- The Trust Admin role: a Researcher who also decides for one trust, assigned from the Users tab, Register User or Enroll with an *Administers* trust picker. Each appointment and removal is written to the trust's audit log (#1266, #1298).
- *My Trust*, the Trust Admin's page, with a pending count in the navigation; Trust Admins can read the projects staged at their trust (project page, cohort query and results, models list, imaging status), read-only (#1266).
- Per-trust decisions on the approve endpoint: `declined` alongside `trusts`, each decision stored with its decider, date and `decided_as` (`HUB` / `SITE`) (#1321, #1266). The existing request body still works.
- `Release checks` in this file and in the pre-release checklist: the tutorial suite on both backends, then `make e2e_smoke` (#1306).
- A DICOM service of its own on Helm trusts, a network policy for the PACS hop, and a fixed node port option (#1234).
- Both FL APIs (`flare-fl-api`, `flower-fl-api`) name their build: `/health` returns `version` — the release tag the image was built at, or `sha-<short7>` for a branch build — and their OpenAPI version matches, as the four service APIs already do. flip-api's OpenAPI version now matches its `/api/health` too (#1325).

## :bug: Bug Fixes

<!-- Update this section if a fix lands before the cut. -->

- The Helm trust-seed hook seeds again. SQLAlchemy 2.1 picks psycopg v3 for a bare `postgresql://` URL, which the omop-db seed tools do not install; they and data-access-api now name `psycopg2` in their database URLs, and the seed install honours the 72-hour dependency cooldown (#1310, #1314). A deploy whose `trustData.seed.sourceRef` predates the fix still fails to seed; the chart's `TROUBLESHOOTING.md` has the workaround.

## :white_check_mark: Release checks

<!-- The gates that cannot run in CI: no GitHub-hosted runner has a GPU, and both the suite and the smoke test need real hardware and a full stack. Tick these on the release branch before the tag is cut — this section is the record that the published examples and the platform path were run, and it is shared by both release trains. See *Pre-release checklist* in CONTRIBUTING.md. -->

Tutorial suite, on a GPU host:

- [ ] NVFLARE — `make -C fl-tutorials run-all-tutorials`
- [ ] Flower — `make -C fl-tutorials run-all-tutorials FL_BACKEND=flower`
- [ ] Host and date recorded: <!-- e.g. "RTX 5090 workstation, 24 September 2026" -->

Not run for v0.10.0: the release was cut the same day as its last changes merged, and the suite takes several hours per backend.

Full-platform smoke test, against a running deployment:

- [x] NVFLARE — `make e2e_smoke`
- [x] Flower — `make e2e_smoke FL_BACKEND=flower`

Both passed on 28 September 2026 on the dev stack on an RTX 5090 workstation, against one trust (`--trusts GSTT`), with the hub, the trust services and the FL images (`sha-2741573`) all at the release commit: create project, cohort query, trust approval, image pull, training, results uploaded and downloaded.

## :file_folder: PRs merged in this release

<!-- auto-populated by the release workflow -->

## :star: Acknowledgements

A big thank you to the following contributors for their work on this release:

<!-- auto-populated by the release workflow -->

---
