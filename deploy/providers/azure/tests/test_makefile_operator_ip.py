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
"""The operator's IP is looked up once, and only an IPv4 answer is kept (FLIP#1390).

The api.ipify.org answer reaches a shell inside double quotes (plan, destroy, kit-upload's
refusal), so anything else in it would run on the operator's machine. These tests run the real
`destroy` target with az, terraform and curl stubbed on PATH.
"""

from __future__ import annotations

import pytest
from conftest import run_make


def _destroy(tmp_path, answers: list[str]) -> list[str]:
    key = tmp_path / "id.pub"
    key.write_text("ssh-ed25519 AAAA test\n")
    result, calls = run_make(tmp_path, "destroy", ipify=answers, SSH_PUBLIC_KEY_FILE=str(key))
    assert result.returncode == 0, result.stdout + result.stderr
    return calls


def _operator_ip(calls: list[str]) -> str:
    (call,) = [c for c in calls if c.startswith("terraform -chdir=vm destroy")]
    return call.split("operator_ip=", 1)[1]


def test_the_looked_up_ip_reaches_terraform(tmp_path):
    calls = _destroy(tmp_path, ["203.0.113.7"])

    assert _operator_ip(calls) == "203.0.113.7"


def test_the_ip_is_looked_up_once_per_run(tmp_path):
    calls = _destroy(tmp_path, ["203.0.113.7", "198.51.100.1"])

    assert len([c for c in calls if c.startswith("curl ")]) == 1, calls


@pytest.mark.parametrize(
    "answer",
    ['203.0.113.7"; touch PWNED; "', "203.0.113.7`touch PWNED`", "<html>busy</html>", ""],
)
def test_an_answer_that_is_not_one_ipv4_address_never_reaches_the_shell(tmp_path, answer):
    sentinel = str(tmp_path / "PWNED")
    calls = _destroy(tmp_path, [answer.replace("PWNED", sentinel)])

    assert not (tmp_path / "PWNED").exists(), "the answer was run as a command"
    assert _operator_ip(calls) == "", "nothing but an IPv4 address is kept"
