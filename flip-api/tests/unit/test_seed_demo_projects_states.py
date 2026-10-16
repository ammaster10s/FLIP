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

"""Unit tests for the demo project seeder's --states subset selection (select_entries) and --member access."""

import json
from typing import Any

import pytest
import requests

from tests import seed_demo_projects
from tests.e2e_smoke import SmokeFailure
from tests.seed_demo_projects import add_member, build_project, select_entries

CATALOGUE = [
    {"name": "Spleen", "state": "approved_model"},
    {"name": "Pneumothorax", "state": "staged"},
    {"name": "Cardiomegaly", "state": "unstaged"},
]


def test_no_selection_returns_full_catalogue() -> None:
    assert select_entries(CATALOGUE, None) == CATALOGUE
    assert select_entries(CATALOGUE, "") == CATALOGUE


def test_selects_requested_states_only() -> None:
    assert select_entries(CATALOGUE, "staged,unstaged") == CATALOGUE[1:]


def test_whitespace_and_empty_tokens_are_tolerated() -> None:
    assert select_entries(CATALOGUE, " staged , ,unstaged ") == CATALOGUE[1:]


def test_unknown_state_raises_with_known_ladder() -> None:
    with pytest.raises(SmokeFailure, match="Unknown --states value.*bogus.*unstaged"):
        select_entries(CATALOGUE, "staged,bogus")


MEMBER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
OWNER = "33333333-3333-3333-3333-333333333333"


def _response(body: Any, status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    return response


class FakeHub(requests.Session):
    """One project readable by GET; every PUT is recorded."""

    def __init__(self, project: dict[str, Any]) -> None:
        super().__init__()
        self.project = project
        self.puts: list[dict[str, Any]] = []

    def read(self, client, path: str, headers) -> requests.Response:  # signature of tests.e2e_smoke._get
        return _response(self.project)

    def put(self, url, data=None, **kwargs) -> requests.Response:
        self.puts.append(kwargs["json"])
        return _response(self.project)


def _project(status: str, users: list[str]) -> dict[str, Any]:
    return {"id": "p1", "name": "Spleen", "description": "d", "status": status, "ownerId": OWNER,
            "users": [{"id": u} for u in users]}  # fmt: skip


def _hub(monkeypatch: pytest.MonkeyPatch, project: dict[str, Any]) -> FakeHub:
    hub = FakeHub(project)
    monkeypatch.setattr(seed_demo_projects, "_get", hub.read)
    return hub


def test_member_is_given_access_when_a_project_is_created(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[dict[str, Any]] = []

    def post(client, path: str, payload: dict[str, Any], headers) -> requests.Response:
        posted.append(payload)
        return _response({"id": "p1"})

    monkeypatch.setattr(seed_demo_projects, "_post", post)

    build_project(requests.Session(), {}, {"name": "Spleen", "description": "d", "state": "unstaged"}, [], [MEMBER])

    assert posted[0]["users"] == [MEMBER]


def test_member_is_added_to_an_existing_unstaged_project(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _hub(monkeypatch, _project("UNSTAGED", [OTHER]))

    add_member(hub, {}, {"id": "p1", "name": "Spleen"}, MEMBER)

    assert hub.puts == [{"name": "Spleen", "description": "d", "users": [OTHER, MEMBER]}]


@pytest.mark.parametrize("status", ["STAGED", "APPROVED"])
def test_a_staged_or_approved_project_is_reported_not_edited(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    hub = _hub(monkeypatch, _project(status, []))

    add_member(hub, {}, {"id": "p1", "name": "Spleen"}, MEMBER)

    assert hub.puts == []


def test_an_existing_member_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _hub(monkeypatch, _project("UNSTAGED", [MEMBER]))

    add_member(hub, {}, {"id": "p1", "name": "Spleen"}, MEMBER)

    assert hub.puts == []
