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

"""Integration coverage of the FL job watchdog (#727) against the throwaway Postgres.

The FLJob -> FLScheduler -> FLNets -> Model join and the model-row lock are SQL-shaped, so mocked sessions would
pass them silently.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from flip_api.db.models.main_models import FLJob, FLNets, FLScheduler
from flip_api.domain.schemas.status import JobStatus, ModelStatus, NetStatus, ProjectStatus
from flip_api.domain.schemas.types import FLBackend
from flip_api.fl_services.watch_jobs import find_watched_jobs


@pytest.fixture
def running_job(session, user_factory, project_factory, model_factory):
    """A model RUNNING on net BUSY with job IN_PROGRESS, submitted to the backend as ``run-1``."""
    user = user_factory()
    project = project_factory.build(owner_id=user.id, status=ProjectStatus.APPROVED, deleted=False)
    session.add(project)
    session.flush()

    model = model_factory.build(project_id=project.id, owner_id=user.id, status=ModelStatus.RUNNING, deleted=False)
    session.add(model)
    session.flush()

    net = FLNets(name=f"net-{uuid4()}", endpoint=f"http://fl-api-{uuid4()}:8000", fl_backend=FLBackend.NVFLARE)
    session.add(net)
    session.flush()

    job = FLJob(
        model_id=model.id,
        status=JobStatus.IN_PROGRESS,
        started=datetime.utcnow() - timedelta(hours=1),
        fl_backend_job_id="run-1",
    )
    session.add(job)
    session.flush()

    scheduler = FLScheduler(net_id=net.id, status=NetStatus.BUSY, job_id=job.id)
    session.add(scheduler)
    session.commit()

    return {"model": model, "job": job, "scheduler": scheduler, "net": net, "user": user, "project": project}


def test_find_watched_jobs_returns_the_running_job_with_its_net(session, running_job):
    watched = find_watched_jobs(session)

    assert [(w.job_id, w.model_id, w.fl_backend_job_id, w.net_name, w.net_endpoint) for w in watched] == [
        (
            running_job["job"].id,
            running_job["model"].id,
            "run-1",
            running_job["net"].name,
            running_job["net"].endpoint,
        )
    ]


@pytest.mark.parametrize("model_status", [ModelStatus.RESULTS_UPLOADED, ModelStatus.ERROR, ModelStatus.STOPPED])
def test_find_watched_jobs_skips_a_model_that_has_ended(session, running_job, model_status):
    running_job["model"].status = model_status
    session.commit()

    assert find_watched_jobs(session) == []


def test_find_watched_jobs_skips_an_older_deleted_job_of_a_requeued_model(session, running_job):
    # Review Focus 4: a stopped-then-requeued model keeps its earlier DELETED job; only the current one counts.
    old = FLJob(model_id=running_job["model"].id, status=JobStatus.DELETED, fl_backend_job_id="run-0")
    session.add(old)
    session.flush()
    session.add(FLScheduler(net_id=running_job["net"].id, status=NetStatus.BUSY, job_id=old.id))
    session.commit()

    assert [w.fl_backend_job_id for w in find_watched_jobs(session)] == ["run-1"]


def test_find_watched_jobs_skips_a_released_net(session, running_job):
    running_job["scheduler"].status = NetStatus.AVAILABLE
    session.commit()

    assert find_watched_jobs(session) == []
