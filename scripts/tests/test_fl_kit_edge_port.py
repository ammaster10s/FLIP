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

"""NVFLARE trust kits dial the LZA edge port of their own estate (FLIP#1365).

Production and staging share one edge NLB address: ``:8002`` forwards to production's FL server and
``:8003`` to staging's, which itself listens on 8002. A client's ``connect_to.port`` (NVFLARE falls
back to the server's ``fed_learn_port`` when it is absent) is therefore the only thing choosing the
estate. Staging kits once came from an edited copy of the template; re-provisioning from the tree
then minted kits that reached production's listener and failed its TLS handshake.

Stdlib-only and executable as a plain script, like the rest of ``scripts/tests``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PROVISION = Path(__file__).resolve().parents[2] / "fl-services" / "nvflare" / "provision"

# project file -> (server fed_learn_port, port every client must dial)
EXPECTED = {
    "net-1_project_prod.yml": (8002, 8002),
    "net-1_project_stag.yml": (8002, 8003),
}


def participants(path: Path) -> list[str]:
    """The text of each ``participants:`` entry in an NVFLARE project file."""
    body = re.search(r"^participants:\n(.*?)(?=^[A-Za-z])", path.read_text(), re.M | re.S)
    assert body, f"no participants block in {path}"
    return re.split(r"^  - ", body.group(1), flags=re.M)[1:]


def port(entry: str, key: str) -> int | None:
    match = re.search(rf"^\s+{key}: (\d+)\s*$", entry, re.M)
    return int(match.group(1)) if match else None


class EdgePort(unittest.TestCase):
    def test_clients_dial_their_estates_edge_port(self):
        for name, (server_port, client_port) in EXPECTED.items():
            entries = participants(PROVISION / name)
            servers = [e for e in entries if re.search(r"^\s+type: server$", e, re.M)]
            clients = [e for e in entries if re.search(r"^\s+type: client$", e, re.M)]
            assert len(servers) == 1, name
            assert clients, name
            assert port(servers[0], "fed_learn_port") == server_port, name
            for client in clients:
                assert (port(client, "port") or server_port) == client_port, f"{name}: {client.splitlines()[0]}"


if __name__ == "__main__":
    unittest.main()
