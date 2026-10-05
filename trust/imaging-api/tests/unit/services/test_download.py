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


"""Download URL checks bypass request schemas and exercise Requests' preparation."""

from urllib.parse import urlsplit

import pytest

from imaging_api.services.download import download_file, format_download_url


def test_identifiers_stay_in_one_segment_at_http_boundary(xnat_path_segment, tmp_path, sent_xnat_requests):
    raw, encoded = xnat_path_segment
    url = format_download_url(raw, raw, raw, resource_type=raw)
    download_file(url, str(tmp_path / "images.zip"), {"X-Request-ID": "trace-1"})

    assert len(sent_xnat_requests) == 1
    request = sent_xnat_requests[0]
    parsed = urlsplit(request.url)
    assert parsed.path == (
        f"/data/projects/{encoded}/subjects/{encoded}/experiments/{encoded}/scans/ALL/resources/{encoded}/files"
    )
    assert parsed.query == "format=zip"
    assert parsed.fragment == ""
    assert request.headers["X-Request-ID"] == "trace-1"


@pytest.mark.parametrize("invalid", ["", ".", ".."])
@pytest.mark.parametrize("field", ["project_id", "subject_id", "experiment_id_or_label", "resource_type"])
def test_empty_and_dot_segments_fail_before_http(field, invalid, sent_xnat_requests):
    kwargs = {"project_id": "PROJ", "subject_id": "SUBJ", "experiment_id_or_label": "EXP", field: invalid}
    with pytest.raises(ValueError, match="empty or a dot-segment"):
        format_download_url(**kwargs)
    assert sent_xnat_requests == []
