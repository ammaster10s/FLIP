# Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Static guard: the ECS Flower SuperLink runs apps with no per-run dependency install (FLIP#1418).

The SuperLink ``uv sync``-s an app's ``pyproject.toml`` into a per-run environment at every launch
unless ``FLWR_DISABLE_RUNTIME_DEPENDENCY_INSTALLATION`` is exactly ``"1"``. A cold sync outlives Flower's
task heartbeat, so the run never starts. Until FLIP#1418 the ECS task set the variable only on LZA
estates, as the second argument of a ``merge`` behind ``var.lza_managed_network``, so every other estate
kept the install. This pins the variable into the unconditional part of the SuperLink's task
environment. The compose and Helm shapes are held to the same rule by
``scripts/tests/test_flower_runtime_install.py``.
"""

import re
from pathlib import Path

from tf_source import hcl_block, strip_comments

AWS_PROVIDER_DIR = Path(__file__).resolve().parent.parent
LOCALS_TF = AWS_PROVIDER_DIR / "locals.tf"
ECS_TASKS_TF = AWS_PROVIDER_DIR / "ecs_tasks.tf"

SUPERLINK_MAP = "fl_server_flower"
DISABLE_LINE = re.compile(r'^\s*FLWR_DISABLE_RUNTIME_DEPENDENCY_INSTALLATION\s*=\s*"1"\s*$', re.MULTILINE)


def test_superlink_task_env_disables_runtime_install_unconditionally() -> None:
    """The variable sits, set to "1", in the first map literal of the SuperLink's task environment.

    ``hcl_block`` returns the first ``{ ... }`` after the header. With ``merge({...}, cond ? {...} : {})``
    that is the unconditional argument, so moving the variable back behind a conditional fails here; and
    a conditional placed *before* that first brace is caught by the prefix check.
    """
    ecs_task_env = hcl_block(strip_comments(LOCALS_TF.read_text()), "ecs_task_env = {")
    header = f"{SUPERLINK_MAP} ="
    start = ecs_task_env.index(header)
    prefix = ecs_task_env[start : ecs_task_env.index("{", start)]
    assert "?" not in prefix, (
        f"{SUPERLINK_MAP} opens with a conditional ({prefix.strip()!r}); the install must be off on every estate"
    )
    assert DISABLE_LINE.search(hcl_block(ecs_task_env, header)), (
        f'{SUPERLINK_MAP} must set FLWR_DISABLE_RUNTIME_DEPENDENCY_INSTALLATION = "1" unconditionally: flwr honours '
        f"only that exact value, and without it a cold per-run uv sync outlives the task heartbeat (FLIP#1418)"
    )


def test_flower_superlink_task_uses_that_map() -> None:
    """The ECS fl-server task takes its Flower environment from the map the test above checks."""
    assert f"local.ecs_task_env.{SUPERLINK_MAP}" in strip_comments(ECS_TASKS_TF.read_text())
