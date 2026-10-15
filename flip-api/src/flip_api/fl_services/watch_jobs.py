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

"""Hub-side watchdog for FL jobs that end without reporting a result (#727).

A job's server-side process reports its own terminal status (RESULTS_UPLOADED, ERROR, ...) to the hub. If that
process dies first, nothing does: the model stays RUNNING and its net BUSY. This compares every job the hub believes
is running with its net's FL API and fails the ones the backend has ended or lost.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlmodel import Session, col, select

from flip_api.db.models.main_models import FLJob, FLNets, FLScheduler, Model
from flip_api.domain.interfaces.fl import IJobMetaData
from flip_api.domain.schemas.status import FLJobStatus, JobStatus, ModelStatus, NetStatus

_ALIVE = {FLJobStatus.PENDING, FLJobStatus.RUNNING}

# Worst first: if a backend ever lists one job id twice, the reason names the worse ending.
_ENDED = {
    FLJobStatus.FAILED: "The FL server on {net} reports this job failed before it reported a result.",
    FLJobStatus.STOPPED: "The FL server on {net} stopped this job before it reported a result.",
    FLJobStatus.FINISHED: "The FL server on {net} finished this job, but its result never reached FLIP.",
}


@dataclass(frozen=True)
class WatchedJob:
    """A job the hub believes is running, with the net it runs on."""

    job_id: UUID
    model_id: UUID
    fl_backend_job_id: str | None
    started: datetime | None
    net_name: str
    net_endpoint: str


# A model in one of these was picked up and has not reported a terminal status.
RUNNING_MODEL_STATUSES = (ModelStatus.INITIATED, ModelStatus.PREPARED, ModelStatus.RUNNING)


def find_watched_jobs(session: Session) -> list[WatchedJob]:
    """List the jobs the hub believes are running: picked up, holding a BUSY net, model not ended.

    Args:
        session (Session): The database session.

    Returns:
        list[WatchedJob]: One entry per running job.
    """
    statement = (
        select(FLJob, FLNets)
        .join(FLScheduler, col(FLScheduler.job_id) == FLJob.id)
        .join(FLNets, col(FLNets.id) == FLScheduler.net_id)
        .join(Model, col(Model.id) == FLJob.model_id)
        .where(
            FLJob.status == JobStatus.IN_PROGRESS,
            FLScheduler.status == NetStatus.BUSY,
            col(Model.status).in_(RUNNING_MODEL_STATUSES),
        )
    )
    return [
        WatchedJob(
            job_id=job.id,
            model_id=job.model_id,
            fl_backend_job_id=job.fl_backend_job_id,
            started=job.started,
            net_name=net.name,
            net_endpoint=net.endpoint,
        )
        for job, net in session.exec(statement).all()
    ]


def why_job_is_dead(
    job: WatchedJob,
    backend_jobs: list[IJobMetaData] | None,
    now: datetime,
    prepare_timeout: timedelta,
) -> str | None:
    """Say why a job the hub believes is running has in fact ended, or None if it has not.

    Args:
        job (WatchedJob): The job.
        backend_jobs (list[IJobMetaData] | None): Every job on the job's net, or None if its FL API could not say.
        now (datetime): The current UTC time, naive like ``FLJob.started``.
        prepare_timeout (timedelta): How long after pickup a job may still have no backend id.

    Returns:
        str | None: The log line to show on the model, or None while the job is alive or its state unknown.
    """
    if job.fl_backend_job_id is None:
        if job.started is not None and now - job.started > prepare_timeout:
            minutes = int(prepare_timeout.total_seconds() // 60)
            return (
                f"Training never reached the FL server on {job.net_name}: "
                f"it was still being prepared after {minutes} minutes."
            )
        return None

    if backend_jobs is None:
        return None

    statuses = {j.status for j in backend_jobs if j.job_id == job.fl_backend_job_id}
    if not statuses:
        return f"The FL server on {job.net_name} no longer has this job, for example because it restarted."
    if statuses & _ALIVE:
        return None
    for status, reason in _ENDED.items():
        if status in statuses:
            return reason.format(net=job.net_name)
    return None
