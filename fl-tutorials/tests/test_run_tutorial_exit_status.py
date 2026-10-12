# Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# run-tutorial.sh's exit status is the release check's verdict (FLIP#1432): `run-all-tutorials
# FL_BACKEND=flower` stops on the first non-zero exit, so a run that did not FINISH must not exit 0.
# It used to: STOPPED and a timeout printed a warning and returned 0, so an unfinished tutorial
# counted as a pass.
#
# The real script runs from a throwaway git checkout (it derives REPO_ROOT from git and the data
# paths from its own location) against a fake `docker` on PATH. The fake answers `compose ... exec
# fl-api python -c <code>` by what the code asks for (health, submit_tutorial, list_runs), lists
# both SuperNodes as running unless told otherwise, and logs every compose invocation so the GPU
# overlay choice can be read back. A fake `nvidia-smi` stands in for the host's GPU.

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RUN_TUTORIAL = Path(__file__).resolve().parents[1] / "flower" / "run-tutorial.sh"
TUTORIAL = "xray_classification"

# FAKE_STATUSES: one /list_runs answer per poll, comma-separated, the last repeating.
FAKE_DOCKER = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_DOCKER_LOG"
case " $* " in
  *" exec "*"/health"*) exit 0 ;;
  *" exec "*"submit_tutorial"*)
    [ -n "${FAKE_SUBMIT_FAIL:-}" ] && { echo "submit failed: HTTP 500: Flower run failed: boom" >&2; exit 1; }
    echo '"4242"' ;;
  *" exec "*"list_runs"*)
    n=$(cat "$FAKE_POLLS" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_POLLS"
    printf '%s' "$FAKE_STATUSES" | awk -v n="$n" -F, '{ i = (n > NF) ? NF : n; print $i }' ;;
  *" ps "*"--status running"*)
    echo supernode-1
    [ -n "${FAKE_SUPERNODE_2_DOWN:-}" ] || echo supernode-2 ;;
  *) exit 0 ;;
esac
"""


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A minimal git checkout holding run-tutorial.sh, one tutorial and its dev data."""
    root = tmp_path / "repo"
    flower = root / "fl-tutorials" / "flower"
    (flower / TUTORIAL / "app").mkdir(parents=True)
    shutil.copy(RUN_TUTORIAL, flower / "run-tutorial.sh")
    data = root / "fl-tutorials" / "data" / "xrays_mini_300"
    (data / "accession-resources").mkdir(parents=True)
    (data / "dataframe.csv").write_text("accession_id\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _run(checkout: Path, tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in {
        "docker": FAKE_DOCKER,
        "nvidia-smi": '#!/usr/bin/env bash\nexit "${FAKE_NVIDIA_RC:-1}"\n',
    }.items():
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "docker.log"
    run_env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_DOCKER_LOG": str(log),
        "FAKE_POLLS": str(tmp_path / "polls"),
        "FAKE_STATUSES": "FINISHED",
        **env,
    }
    proc = subprocess.run(
        ["bash", str(checkout / "fl-tutorials" / "flower" / "run-tutorial.sh"), TUTORIAL],
        env=run_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc, log.read_text() if log.exists() else ""


def test_finished_run_exits_zero(checkout, tmp_path):
    proc, _ = _run(checkout, tmp_path, FAKE_STATUSES="FINISHED")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "run FINISHED" in proc.stdout


@pytest.mark.parametrize("status", ["FAILED", "STOPPED"])
def test_unfinished_terminal_status_exits_one(checkout, tmp_path, status):
    proc, _ = _run(checkout, tmp_path, FAKE_STATUSES=status)
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_timeout_exits_one(checkout, tmp_path):
    proc, _ = _run(checkout, tmp_path, FAKE_STATUSES="RUNNING", WAIT_SECS="1")
    assert proc.returncode == 1
    assert "not terminal within 1s" in proc.stdout


def test_supernode_not_running_exits_one_before_submit(checkout, tmp_path):
    proc, log = _run(checkout, tmp_path, FAKE_SUPERNODE_2_DOWN="1")
    assert proc.returncode == 1
    assert "supernode-2 is not running" in proc.stdout
    assert "submit_tutorial" not in log


def test_submit_failure_exits_one_with_the_reason(checkout, tmp_path):
    proc, _ = _run(checkout, tmp_path, FAKE_SUBMIT_FAIL="1")
    assert proc.returncode == 1
    assert "Flower run failed: boom" in proc.stderr


@pytest.mark.parametrize(
    ("env", "overlay"),
    [
        ({"FAKE_NVIDIA_RC": "0"}, True),  # a GPU host
        ({"FAKE_NVIDIA_RC": "1"}, False),  # no usable GPU
        ({"FAKE_NVIDIA_RC": "0", "RUN_TUTORIAL_GPU": "0"}, False),
        ({"FAKE_NVIDIA_RC": "0", "RUN_TUTORIAL_GPU": "false"}, False),
        ({"FAKE_NVIDIA_RC": "1", "RUN_TUTORIAL_GPU": "1"}, True),
    ],
)
def test_gpu_overlay_selection(checkout, tmp_path, env, overlay):
    proc, log = _run(checkout, tmp_path, **env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    up = next(line for line in log.splitlines() if " up -d" in line)
    assert ("compose.dev.gpu.yml" in up) is overlay
