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


"""Upload URL checks cover scan/resource creation and file GET/PUT preparation."""

from urllib.parse import urlsplit

import pytest

from imaging_api.services.upload import create_xnat_resource, create_xnat_scan, upload_file_to_xnat


@pytest.mark.parametrize("sink", ["scan", "resource", "upload"])
def test_identifiers_stay_in_one_segment_at_http_boundary(sink, xnat_path_segment, tmp_path, sent_xnat_requests):
    raw, encoded = xnat_path_segment
    headers = {"X-Request-ID": "trace-1"}
    if sink == "scan":
        create_xnat_scan(raw, raw, raw, raw, headers)
        expected_path = f"/data/projects/{encoded}/subjects/{encoded}/experiments/{encoded}/scans/{encoded}"
        expected_query = "xsiType=xnat:mrScanData"
    elif sink == "resource":
        create_xnat_resource(raw, raw, raw, raw, raw, headers)
        expected_path = (
            f"/data/projects/{encoded}/subjects/{encoded}/experiments/{encoded}/scans/{encoded}/resources/{encoded}"
        )
        expected_query = ""
    else:
        file_path = tmp_path / "image ?#% α.nii.gz"
        file_path.write_bytes(b"image-data")
        uploaded_url = upload_file_to_xnat(raw, raw, raw, raw, raw, str(file_path), exist_ok=False, headers=headers)
        expected_path = (
            f"/data/projects/{encoded}/subjects/{encoded}/experiments/{encoded}/scans/{encoded}/resources/{encoded}"
            "/files/image%20%3F%23%25%20%CE%B1.nii.gz"
        )
        expected_query = "inbody=true"
        assert [request.method for request in sent_xnat_requests] == ["GET", "PUT"]
        assert uploaded_url == sent_xnat_requests[0].url == sent_xnat_requests[1].url

    assert len(sent_xnat_requests) == (2 if sink == "upload" else 1)
    for request in sent_xnat_requests:
        parsed = urlsplit(request.url)
        assert parsed.path == expected_path
        assert parsed.query == expected_query
        assert parsed.fragment == ""
        assert request.headers["X-Request-ID"] == "trace-1"


@pytest.mark.parametrize("invalid", ["", ".", ".."])
@pytest.mark.parametrize(
    ("sink", "field"),
    [
        ("scan", "project_id"),
        ("scan", "subject_id"),
        ("scan", "experiment_id_or_label"),
        ("scan", "scan_id"),
        ("resource", "project_id"),
        ("resource", "subject_id"),
        ("resource", "experiment_id_or_label"),
        ("resource", "scan_id"),
        ("resource", "resource_id"),
        ("upload", "project_id"),
        ("upload", "subject_id"),
        ("upload", "experiment_id_or_label"),
        ("upload", "scan_id"),
        ("upload", "resource_id"),
    ],
)
def test_empty_and_dot_segments_fail_before_http(sink, field, invalid, tmp_path, sent_xnat_requests):
    kwargs = {
        "project_id": "PROJ",
        "subject_id": "SUBJ",
        "experiment_id_or_label": "EXP",
        "scan_id": "SCAN",
        "headers": {},
        field: invalid,
    }
    call = {"scan": create_xnat_scan, "resource": create_xnat_resource, "upload": upload_file_to_xnat}[sink]
    if sink != "scan":
        kwargs.setdefault("resource_id", "NIFTI")
    if sink == "upload":
        file_path = tmp_path / "image.nii.gz"
        file_path.write_bytes(b"image-data")
        kwargs.update(file_path=str(file_path), exist_ok=False)
    with pytest.raises(ValueError, match="empty or a dot-segment"):
        call(**kwargs)
    assert sent_xnat_requests == []


@pytest.mark.parametrize("file_path", ["", ".", ".."])
def test_unusable_upload_filename_fails_before_http(file_path, sent_xnat_requests):
    with pytest.raises(ValueError, match="empty or a dot-segment"):
        upload_file_to_xnat("PROJ", "SUBJ", "EXP", "SCAN", "NIFTI", file_path, exist_ok=False, headers={})
    assert sent_xnat_requests == []
