---
description: Prepare or cut a FLIP platform release using the repository release process
argument-hint: "[version, e.g. v0.13.0] [prepare|gates|record|main|post-merge] [gpu-host, e.g. bioeng625-pc]"
allowed-tools: Bash(gh:*), Bash(git:*), Bash(make:*), Bash(uv:*), Bash(ssh:*), Bash(docker:*), Bash(curl:*), Read, Edit, Write, Grep, Glob
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

Target: **$ARGUMENTS** (default: the next minor after the latest `v*.*.*` tag; mode `prepare`).

Read `.agents/skills/release/SKILL.md` and follow it. That file is shared with other agents and holds the
procedure, the scope limits and the GPU-host gates. Also read the CONTRIBUTING section it points to.

On top of it, for Claude Code:

- **GPU host.** If this session is not on the GPU host (a laptop or Mac), every gate runs there over SSH. Only
  `gh`/`git` and notes work stays local. Take the host from the arguments, or else from memory. Ask only if
  neither has it, and name the example: the core team uses `bioeng625-pc`. Use the user's own SSH alias for it,
  and check it with `ssh <alias> 'nvidia-smi -L && docker info -f {{.Name}}'` before starting any gate.
  Non-interactive SSH may not load the login PATH, so tools such as `uv` in `~/.local/bin` can be missing. Export
  the PATH in each gate script.
- **Resume, don't restart.** Look for an open `Release v<X.Y.Z>` PR and an existing `release-v<X.Y.Z>`
  worktree, both locally and on the GPU host, and pick up from the first unticked step.
- **Memory.** If your memory has release notes or owed items tied to "next release" or "release→main", such as
  GitHub environment variable cleanups, put them in the `main`-PR body as after-merge steps. Also follow any
  turn-taking rules it records for the shared host.
- **Remote gates.** Start each gate with `run_in_background`
  (`ssh <alias> 'cd <wt> && make … > ~/e2e-logs/release-v<X.Y.Z>/<gate>.log 2>&1'`) and wait for it with
  Monitor. Don't poll in a loop. If the host needs `sudo`, give the user the command with `!`. To stop a remote
  process, kill it by PID or use a bracketed pattern (`pgrep -f "[e]2e_smoke"`). A bare `pkill -f <pattern>`
  matches the SSH shell that carries the pattern and kills that shell first.
- **Images.** Before each smoke, list the instance's containers with their images. Any repo-built image not at the
  release tag (`:stag`, `:dev`, `:latest`) means the gate did not test the release head.
- **Parallelism.** Run the Dependabot fixes, labelling and notes curation while the remote gates run.
- **Report.** End with a checklist that marks each gate passed, pending or failed, gives its evidence (host,
  SHA, log path, timings), and lists the PR links with their reviewer requests verified.
