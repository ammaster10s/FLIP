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
"""Shared paths and helpers for the Azure deploy static tests (FLIP#1390)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

AZURE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AZURE_DIR.parent.parent.parent

STUB_AZ = """#!/bin/bash
printf '%s\\n' "$*" >> "$AZ_LOG"
case "$1 $2" in
    "account show") echo 00000000-0000-0000-0000-000000000000 ;;
    "vm run-command") echo ok ;;
esac
"""

# Terraform never runs for real here: it logs its arguments and answers any `output` with a stub.
STUB_TERRAFORM = """#!/bin/bash
printf 'terraform %s\\n' "$*" >> "$AZ_LOG"
echo stub
"""

# api.ipify.org: answers the Nth lookup with the Nth line of $IPIFY_ANSWERS, then repeats the last.
STUB_CURL = """#!/bin/bash
printf 'curl %s\\n' "$*" >> "$AZ_LOG"
n=$(grep -c '^curl ' "$AZ_LOG")
total=$(wc -l < "$IPIFY_ANSWERS")
sed -n "$(( n < total ? n : total ))p" "$IPIFY_ANSWERS"
"""


def run_make(
    tmp_path: Path, target: str, ipify: list[str] | None = None, **variables: str
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run a real Makefile target with `az` stubbed on PATH; return the result and every stubbed call.

    `terraform` is always stubbed. With `ipify`, `curl` is stubbed too and answers the IP lookups in
    that order. az calls are logged bare, the others as `terraform ...` and `curl ...`.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stubs = {"az": STUB_AZ, "terraform": STUB_TERRAFORM, **({"curl": STUB_CURL} if ipify is not None else {})}
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "az.log"
    log.touch()
    answers = tmp_path / "ipify.txt"
    answers.write_text("".join(f"{a}\n" for a in ipify or []))
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "AZ_LOG": str(log), "IPIFY_ANSWERS": str(answers)}
    args = [f"{k}={v}" for k, v in {"AZ_SUBSCRIPTION": "trial", **variables}.items()]
    result = subprocess.run(
        ["make", "-s", "-C", str(AZURE_DIR), target, *args],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, log.read_text().splitlines()
