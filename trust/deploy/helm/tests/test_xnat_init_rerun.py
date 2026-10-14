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

"""``make xnat-init`` re-runs the configuration even when an earlier xnat-init Job still exists."""

import subprocess
from pathlib import Path

CHART_DIR = Path(__file__).resolve().parents[1]


def test_a_rerun_deletes_the_previous_init_job_before_applying_it() -> None:
    """Left in place, the apply reports the Job unchanged and the wait passes at once on the old one."""
    recipe = subprocess.run(
        ["make", "-n", "xnat-init", "KUBE_CONTEXT=test"], cwd=CHART_DIR, capture_output=True, text=True, check=True
    ).stdout.replace("\\\n", " ")

    delete = next(line for line in recipe.splitlines() if " delete job " in line)
    assert "--selector app.kubernetes.io/component=xnat-init" in delete
    assert "--ignore-not-found" in delete
    assert recipe.index(" delete job ") < recipe.index(" apply -n ") < recipe.index(" wait job")
