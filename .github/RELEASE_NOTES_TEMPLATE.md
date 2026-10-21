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

- **A security patch for v0.13.0** (#1612). Dependencies with open security advisories are upgraded: certifi and uv
  (critical) across the Python services and FL images, Pillow (critical/high) in flip-utils and the FL images, and
  vite and follow-redirects (high/medium) in flip-ui. No FLIP code or behaviour changes.

## :warning: Breaking Changes

- None. Pillow moves to 13.0, a major release; no FLIP code uses the APIs it removes. Researcher FL code that calls
  Pillow directly should check the [Pillow 13.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).

## :arrows_counterclockwise: Site upgrade

<!-- The prompt to trust operators (FLIP#1204). Sites upgrade on their own schedule and to the
     release their hub runs; this section is how they learn what this release asks of them. -->

- **Required:** recommended, not required. The release carries security fixes only; a v0.13.0 site keeps working
  with a v0.13.1 hub. Sites on v0.12.x or earlier must first follow the v0.13.0 notes (one coordinated window and a
  cohort-snapshot backfill).
- **Ordering:** any order. The hub and the sites can move independently.
- **Kubernetes trusts:** recommended, as for on-prem sites.
- **Refreshed kit needed:** no. The Hub-shared block is unchanged.
- **Operator command**, on the trust host, from your FLIP checkout:
  ```bash
  git fetch --tags origin && git checkout {{TAG}}        # the compose files and the verb come from the checkout, not the images
  sudo -E make upgrade-onprem-trust KIT=<slot>           # defaults to the release the hub now reports
  ```
  Kubernetes: `make -C trust/deploy/helm upgrade-trust-k8s KIT=<CODE> PROD=<env> TAG={{TAG}}`; EC2: `make -C deploy/providers/AWS upgrade-trust-ec2 KIT=<CODE> PROD=<env> TAG={{TAG}}`, both from a checkout at {{TAG}}. Runbook: *docs → System administrators → Upgrading a site*.

## :bug: Bug Fixes

- Security: certifi 2026.10.19 (GHSA-6q48-6c7w-9gw2) in every Python service and FL image; uv 0.13.4
  (GHSA-hq85-5cpj-mr62) in flip-utils and the Flower FL API; Pillow 13.0.0 (nine advisories) in flip-utils; vite
  8.1.6 and follow-redirects 1.16.1 in flip-ui (#1612).

## :white_check_mark: Release checks

<!-- These checks are release evidence and must be run for v0.13.1. Do not carry forward results
     from an earlier release. Record the host, date and outcome before merging the release PR. -->

Tutorial suite, on a GPU host:

- [ ] FLARE — `make -C fl-tutorials run-all-tutorials`
- [ ] Flower — `make -C fl-tutorials run-all-tutorials FL_BACKEND=flower`
- [ ] Host, date, and results recorded

Full-platform smoke test, against a running deployment:

- [ ] FLARE — `make e2e_smoke`
- [ ] Flower — `make e2e_smoke FL_BACKEND=flower`
- [ ] Host, date, deployment, and results recorded

Local checks:

- [ ] `make unit_test`
- [ ] `make integration_test`

## :file_folder: PRs merged in this release

<!-- auto-populated by the release workflow -->

## :star: Acknowledgements

A big thank you to the following contributors for their work on this release:

<!-- auto-populated by the release workflow -->
