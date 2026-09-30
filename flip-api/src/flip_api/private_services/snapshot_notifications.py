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

"""Post-processing of completed PERSIST_COHORT tasks (FLIP#857).

Records the hub's audit row for the cohort membership a trust froze at approval — the answer to
"what cohort was this project approved for?" that #857 found missing — and surfaces
membership drift against the count the project was approved on. Aggregates only: the
row-level cohort never leaves the trust.
"""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, select

from flip_api.db.models.main_models import (
    COHORT_SNAPSHOT_STATUS_UNIQUE,
    CohortSnapshotStatus,
    QueryStats,
    TrustTask,
)
from flip_api.domain.schemas.private import AggregatedCohortStats
from flip_api.utils.logger import logger


def _approved_record_count(query_id: UUID | None, trust_id: UUID | None, db: Session) -> int | None:
    """The per-trust cohort count the project was staged/approved on, if recorded.

    Read from the aggregated statistics blob captured at submission time
    (``AggregatedCohortStats.trust_record_counts``). None when the stats row or the
    trust's entry is missing — old data or an errored trust — which downgrades the drift
    check to "not comparable", never blocks the audit row.
    """
    if query_id is None or trust_id is None:
        return None
    stats_row = db.exec(select(QueryStats).where(QueryStats.query_id == query_id)).first()
    if stats_row is None:
        return None
    try:
        stats = AggregatedCohortStats.model_validate(json.loads(stats_row.stats))
    except Exception:
        logger.warning(f"Could not parse QueryStats for query {query_id}; skipping drift comparison")
        return None
    return stats.trust_record_counts.get(str(trust_id))


def handle_snapshot_task_completed(task: TrustTask, db: Session) -> None:
    """Persist the frozen-cohort audit row for a successful PERSIST_COHORT task.

    Upserts the one ``CohortSnapshotStatus`` row per (project, trust) with a single
    ``INSERT ... ON CONFLICT DO UPDATE`` on the table's unique constraint, so a re-approval
    (or two post-processing runs racing — submission and the recovery job) updates the row
    in place rather than duplicating it or failing on the constraint. The row holds the
    approval-time facts; the frozen membership bounds what the project trains on at that
    trust (it can shrink, never grow). Logs a WARNING when the frozen member count differs
    from the count the project was approved on: the live cohort drifted between submission
    and approval. The drift is surfaced, never acted on.

    Called after the task result has been committed to the database.
    Any exceptions are expected to be caught by the caller.

    Args:
        task (TrustTask): The completed PERSIST_COHORT task with result data.
        db (Session): Database session.

    Raises:
        ValueError: If the task has no result data.
    """
    if not task.result:
        raise ValueError(f"Task {task.id} has no result data")
    snapshot = json.loads(task.result)

    payload = json.loads(task.payload)
    project_id = UUID(payload["project_id"])
    query_id = UUID(payload["query_id"]) if payload.get("query_id") else None

    row_count = int(snapshot["row_count"])
    approved_count = _approved_record_count(query_id, task.trust_id, db)
    if approved_count is not None and approved_count != row_count:
        logger.warning(
            f"Cohort membership drift for project {project_id}, trust {task.trust_id}: approved on "
            f"{approved_count} records, frozen membership holds {row_count}. The live cohort changed "
            "between submission and approval; the frozen membership bounds what the project trains on."
        )

    facts = {
        "query_id": query_id,
        "row_count": row_count,
        "approved_record_count": approved_count,
        "has_accessions": bool(snapshot.get("has_accessions", False)),
        "query_hash": snapshot.get("query_hash"),
        "snapshot_at": datetime.fromisoformat(snapshot["snapshot_at"]),
    }
    statement = (
        pg_insert(CohortSnapshotStatus)
        .values(id=uuid4(), project_id=project_id, trust_id=task.trust_id, created_at=datetime.now(UTC), **facts)
        .on_conflict_do_update(constraint=COHORT_SNAPSHOT_STATUS_UNIQUE, set_=facts)
    )
    db.execute(statement)
    db.commit()
    logger.info(
        f"Recorded cohort snapshot for project {project_id}, trust {task.trust_id}: "
        f"{row_count} members, has_accessions={facts['has_accessions']}"
    )
