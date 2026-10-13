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
"""The AKS API server admits only the operator's current IP, without a Terraform plan (FLIP#1390).

Its allowlist holds one address and an operator's public IP moves (home, office, VPN), so
`make aks-allow-ip` resets it, and `make aks-start` does so once the cluster is up. These tests run
the real targets with `az` stubbed on PATH and read back the calls.
"""

from __future__ import annotations

import pytest
from conftest import run_make

SUB = "00000000-0000-0000-0000-000000000000"


def _aks(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith("aks ")]


def test_allow_ip_admits_exactly_the_operator(tmp_path):
    result, calls = run_make(tmp_path, "aks-allow-ip", OPERATOR_IP="203.0.113.7")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _aks(calls) == [
        f"aks update --subscription {SUB} -g flipaz-aks-rg -n flipaz-aks"
        " --api-server-authorized-ip-ranges 203.0.113.7/32"
    ]


@pytest.mark.parametrize(
    "ip",
    [
        "",  # the api.ipify.org lookup failed
        "203.0.113.0/24",
        "203.0.113.7,198.51.100.1",
        "example.com",
        "203.0.113.7; touch PWNED",
        "203.0.113.7`touch PWNED`",
    ],
)
def test_allow_ip_refuses_anything_but_one_ipv4_address(tmp_path, ip):
    sentinel = str(tmp_path / "PWNED")
    result, calls = run_make(tmp_path, "aks-allow-ip", OPERATOR_IP=ip.replace("PWNED", sentinel))

    assert result.returncode != 0
    assert "OPERATOR_IP=" in result.stdout + result.stderr, "the refusal names the variable"
    assert not _aks(calls), "the allowlist was never touched"
    assert not (tmp_path / "PWNED").exists(), "the value was never run as a command"


def test_start_admits_the_operator_once_the_cluster_is_up(tmp_path):
    result, calls = run_make(tmp_path, "aks-start", OPERATOR_IP="203.0.113.7")

    assert result.returncode == 0, result.stdout + result.stderr
    verbs = [c.split()[1] for c in _aks(calls)]
    assert verbs == ["start", "update"], "a stopped cluster refuses updates, so start comes first"
    assert _aks(calls)[1].endswith("--api-server-authorized-ip-ranges 203.0.113.7/32")
