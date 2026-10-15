# Copyright (c) Guy's and St Thomas' NHS Foundation Trust & King's College London
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

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from flip_api.domain.interfaces.fl import IJobMetaData
from flip_api.domain.schemas.status import FLJobStatus
from flip_api.fl_services.watch_jobs import WatchedJob, why_job_is_dead

NOW = datetime(2026, 10, 14, 12, 0, 0)
PREPARE_TIMEOUT = timedelta(minutes=30)


def _job(fl_backend_job_id: str | None = "run-1", started: datetime | None = NOW - timedelta(hours=1)) -> WatchedJob:
    return WatchedJob(
        job_id=uuid4(),
        model_id=uuid4(),
        fl_backend_job_id=fl_backend_job_id,
        started=started,
        net_name="net-1",
        net_endpoint="http://fl-api-net-1:8000",
    )


def _listed(status: FLJobStatus, job_id: str = "run-1") -> list[IJobMetaData]:
    return [IJobMetaData(job_id=job_id, status=status)]


@pytest.mark.parametrize("status", [FLJobStatus.RUNNING, FLJobStatus.PENDING])
def test_a_running_or_waiting_job_is_alive(status):
    # PENDING covers NVFLARE waiting for resources (#1423), which can last ten scheduler tries.
    assert why_job_is_dead(_job(), _listed(status), NOW, PREPARE_TIMEOUT) is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (FLJobStatus.FAILED, "The FL server on net-1 reports this job failed before it reported a result."),
        (FLJobStatus.STOPPED, "The FL server on net-1 stopped this job before it reported a result."),
        (FLJobStatus.FINISHED, "The FL server on net-1 finished this job, but its result never reached FLIP."),
    ],
)
def test_a_job_the_backend_has_ended_is_dead(status, expected):
    assert why_job_is_dead(_job(), _listed(status), NOW, PREPARE_TIMEOUT) == expected


def test_a_job_the_backend_no_longer_lists_is_dead():
    reason = why_job_is_dead(_job(), _listed(FLJobStatus.RUNNING, job_id="another-run"), NOW, PREPARE_TIMEOUT)

    assert reason == "The FL server on net-1 no longer has this job, for example because it restarted."


def test_an_unreachable_fl_api_says_nothing():
    assert why_job_is_dead(_job(), None, NOW, PREPARE_TIMEOUT) is None


def test_any_live_record_keeps_the_job_alive():
    backend_jobs = _listed(FLJobStatus.FAILED) + _listed(FLJobStatus.RUNNING)

    assert why_job_is_dead(_job(), backend_jobs, NOW, PREPARE_TIMEOUT) is None


def test_a_job_still_being_prepared_is_alive():
    job = _job(fl_backend_job_id=None, started=NOW - timedelta(minutes=29))

    assert why_job_is_dead(job, None, NOW, PREPARE_TIMEOUT) is None


def test_a_job_never_submitted_after_the_timeout_is_dead():
    job = _job(fl_backend_job_id=None, started=NOW - timedelta(minutes=31))

    reason = why_job_is_dead(job, None, NOW, PREPARE_TIMEOUT)

    assert reason == "Training never reached the FL server on net-1: it was still being prepared after 30 minutes."
