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


"""Experiment URL checks include the shared project-listing prerequisite."""

from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
import requests

from imaging_api.services.projects import get_experiment


def test_identifiers_stay_in_one_segment_at_http_boundary(xnat_path_segment, sent_xnat_requests):
    raw, encoded = xnat_path_segment
    with patch("imaging_api.services.projects.get_project"):
        assert get_experiment(raw, raw, {"X-Request-ID": "trace-1"}) == {}

    assert len(sent_xnat_requests) == 1
    request = sent_xnat_requests[0]
    parsed = urlsplit(request.url)
    assert parsed.path == f"/data/projects/{encoded}/experiments/{encoded}"
    assert parsed.query == "format=json"
    assert parsed.fragment == ""
    assert request.headers["X-Request-ID"] == "trace-1"


@pytest.mark.parametrize("invalid", ["", ".", ".."])
@pytest.mark.parametrize("field", ["project_id", "experiment_id_or_label"])
def test_empty_and_dot_segments_fail_before_http(field, invalid, sent_xnat_requests):
    kwargs = {"project_id": "PROJ", "experiment_id_or_label": "EXP", "headers": {}, field: invalid}
    with pytest.raises(ValueError, match="empty or a dot-segment"):
        get_experiment(**kwargs)
    assert sent_xnat_requests == []


def test_experiment_lookup_quotes_identifiers_after_real_project_listing(sent_xnat_requests):
    project_id = "PROJ?format=xml"
    project = {
        "ID": project_id,
        "secondary_ID": "hub-project",
        "name": "Project",
        "pi_firstname": "",
        "pi_lastname": "",
        "URI": "/data/projects/project",
    }
    with patch.object(requests.Response, "json", side_effect=[{"ResultSet": {"Result": [project]}}, {"items": []}]):
        assert get_experiment(project_id, "ACC#fragment", {}) == {"items": []}
    assert [urlsplit(request.url).path for request in sent_xnat_requests] == [
        "/data/projects",
        "/data/projects/PROJ%3Fformat%3Dxml/experiments/ACC%23fragment",
    ]
    assert urlsplit(sent_xnat_requests[1].url).query == "format=json"
