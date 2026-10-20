---
name: release
description: Prepare and cut a FLIP platform release — version bumps, release notes, the pre-release gates on a GPU host, the release PRs, and the post-merge follow-through.
---

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

# FLIP release

[`CONTRIBUTING.md` § Cutting a release](../../../CONTRIBUTING.md#cutting-a-release) is the procedure: versioning
rules, the two tag namespaces, the pre-release checklist, merge rules and roll-out. Read it and
`.github/workflows/release.yml` first; this skill adds only what an agent needs on top and does not restate them.

## Scope and autonomy

Preparation runs unattended, often overnight: discovery, fixes, gates, checklist evidence, PRs into `develop`. Don't
ask routine questions; pick the safe default and record it in the report. Leftovers from an earlier attempt at this
same release (its worktree, isolated stack, orphaned simulator processes, unverified ticks) are yours to replace.
Stop only on a blocker that needs the user, for example a live process owned by someone else, and report it with
what is already done. **Without an explicit request for that specific
action, never** open the `develop` → `main` PR, merge anything, push or create a tag, dispatch a deploy or apply,
attest `fl_quiesced`, or upgrade a site.

## Prepare

1. **State.** Fetch; note `develop`/`main` heads and the latest `v*.*.*` and `flip-utils-v*.*.*` tags. Work in a new
   worktree off `origin/develop` (branch `release-v<X.Y.Z>`); leave the main checkout's untracked files alone.
2. **Scope.** `develop` CI green; every intended PR merged and labelled (`.github/release.yml` categories):
   `gh pr list --base develop --state merged --search "merged:>=<prev tag date>" --json number,title,labels`.
   Label the unlabelled ones before the notes are generated.
3. **Dependabot.** `gh api 'repos/londonaicentre/FLIP/dependabot/alerts?state=open' --paginate`. Fix actionable
   alerts in **separate** PRs, never in the version-bump PR. Recheck after they merge.
4. **Bump PR, opened as a draft early.** Root `pyproject.toml`; each service version only if that service changed;
   `flip-utils/flip/__init__.py` only if `flip-utils/**` changed (strictly above the last `flip-utils-v*` tag);
   lockfiles via `make lock`. Curate `.github/RELEASE_NOTES_TEMPLATE.md`, especially *Site upgrade* (required or
   not, hub/site order or one Deployment-Mode window, refreshed kit or not). Reset every *Release checks* box to
   `[ ]` and delete the previous release's results: old ticks are not evidence. Open as draft
   `Release v<X.Y.Z>` → `develop`; the gates below run at its head.
5. **Gates, at the PR head.** Before each gate, prove the checkout is the PR head and clean:
   `gh pr view <n> --json headRefOid` = `git rev-parse HEAD`, and `git status --porcelain --untracked-files=no`
   empty. The instance's own env and kit files are untracked, and the evidence lists them. If the head moves,
   rerun the gates it affects.
6. **Record and hand off.** Fill *Release checks* with host, date, SHA and per-tutorial / per-backend results;
   push; wait for CI to go green; mark the PR ready; request review from a maintainer other than the person running
   the release (e.g. `garciadias`, or `atriaybagur` when garciadias runs it) and confirm with
   `gh pr view <n> --json reviewRequests`. Any gate still pending stays visibly
   `[ ]` and goes in the report as pending. It is never reported as passed.

## Gates on the GPU host

They run on a Linux host with an NVIDIA GPU and Docker, never on a laptop. For example, the core team uses the
shared dev desktop `bioeng625-pc` over SSH. If the user hasn't named the host, take it from your notes or memory, and
ask only if you find none. Keep a release worktree
there at the PR head, and run long commands in the background with logs under `~/e2e-logs/release-v<X.Y.Z>/`.
If other people use the host, its Docker daemon and default stack are shared. The rules below keep you off both.

- **Tutorials.** Both backends of `make -C fl-tutorials run-all-tutorials`, after the inputs listed in
  CONTRIBUTING (datasets, prostate prep, Ark+ checkpoint). `fl-tutorials/data/` is gitignored, so a new worktree
  starts with none. Point it at the main checkout's copy (symlink) rather than downloading again.
- **Smoke, from empty state.** A second instance, isolated by `FLIP_INSTANCE`, its own `MAIN_ENV_FILE`, its own
  host ports and `CENTRAL_HUB_API_URL`, and its own trust numbers and `XNAT_PORT`s
  ([`deploy/AGENTS.md` § Multi-instance](../../../deploy/AGENTS.md#multi-instance-environment-variables)). Never
  use the host's default `deploy` stack, which may be someone else's. `make up BUILD=true` from the worktree and let
  seeding run from empty volumes. Then run `make e2e_smoke` and `make e2e_smoke FL_BACKEND=flower`, passing the same
  `FLIP_INSTANCE`/`MAIN_ENV_FILE`. Before smoking, prove origin: the containers'
  `com.docker.compose.project.working_dir` is this worktree, they were created after step 5, and `/health`
  where it exists. If you can't prove it, the gate stays pending.
- **Instance setup traps.** `generate-internal-service-key` ignores `MAIN_ENV_FILE` and writes
  `.env.development`. Symlink `.env.development` to the instance's own env file inside the worktree. Never point
  it at another checkout's file: the script writes keys into it. Set `DOCKER_TAG` to a release-only tag, so the
  local builds don't overwrite the shared `:stag`/`:dev`. **Every image the instance runs is built
  from the worktree at that tag; none is pulled.** `make up BUILD=true` does not build `omop-db` or the XNAT images,
  so build them first: `make -C trust/xnat build DOCKER_TAG=<tag>` and `OMOP_DB_TAG=<tag> make -C trust/omop-db
  build`, then set `OMOP_DB_TAG=<tag>` in the instance's kits. Never pin them to `:stag` or `:dev`: those images
  are whatever `develop` last published (or an older copy cached on the host), not the release head. A release can
  change files that are baked into the image (`omop-db`'s init SQL, XNAT's `config/`), and those changes would go
  untested. Without the build, XNAT's swarm services sit at `0/1` on `manifest unknown` and `make up` hangs. Before
  smoking, list each container's image and check that every repo-built image carries the release tag. Run `make -C trust prepare-artifacts` before `up`.
  Fill the example's placeholder secrets before `up`: `AES_KEY_BASE64` must decode to 32 bytes
  (`openssl rand -base64 32`), or every cohort submit returns 500. The smoke runs on the host and does not derive
  URLs from the instance ports: set `KEYCLOAK_PUBLIC_URL=http://localhost:<KEYCLOAK_PORT>` and
  `FLIP_E2E_BASE_URL=http://localhost:<API_PORT>/api` in the env file and the shell. Without them it authenticates
  against, and submits to, the host's **default** hub on 8180/8080.
- **FL images: do not use `:dev`.** `make build-fl` tags `flare-*/flower-*:dev`, and those tags are global to
  the host's Docker daemon. On a shared host, other people's stacks run on them. Build through a compose override that tags
  `:rel<XYZ>` and run with `DOCKER_FL_REGISTRY= DOCKER_FL_TAG=rel<XYZ>`. If the shared tag has to move, ask its
  users first.
- **Suites.** `make unit_test` and `make integration_test` at the same SHA. Run `unit_test` in a checkout whose
  `.env.development` is the plain example: `trust/xnat`'s container-lookup tests read `FLIP_INSTANCE` from it and
  fail under the instance symlink.
- **Teardown** after both smokes are recorded: `make down` with the same instance settings, then `make
  remove-networks FLIP_INSTANCE=<x>`. Check that `docker ps -a` and `docker service ls` show nothing with the
  instance prefix. Leave every other stack, volume and image alone.

## After the bump PR merges (only on request)

Open `develop` → `main` titled `Release v<X.Y.Z> (develop → main)`. Check that it is MERGEABLE, that
`check-version-bump` and `validate_branch_origin` pass, and read the release-notes preview comment. Merge it **with
a merge commit**.

The merge triggers two prod Terraform applies: the push apply at `sha-`, then the `release.yml` apply at
`v<X.Y.Z>` once the twelve image builds are green. Both can hold on the FL gate. Only the user may attest
`fl_quiesced`. Nothing may merge to `main` until the release apply has run.

Then check that the Release page, GHCR `:v<X.Y.Z>` (all twelve) and PyPI (if bumped) are correct, and that prod
`/api/health` reports `v<X.Y.Z>`. flip-ui is **not** deployed by the merge (#1186 is open):
`make -C deploy/providers/AWS deploy-ui PROD=<env>` from a checkout at the tag. Sites upgrade themselves: point
operators to *Site upgrade* and `docs/source/sys-admin/admin-upgrading-sites.rst`.
