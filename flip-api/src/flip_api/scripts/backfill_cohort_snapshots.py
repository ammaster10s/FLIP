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

"""Queue the approval-time cohort freeze (FLIP#857) wherever an approved project has none.

A project approved before cohort snapshots existed holds no frozen membership at any trust, and the trusts
refuse its row-level routes until it does. This queues a PERSIST_COHORT task at every approved trust of every
APPROVED project that has no ``cohort_snapshot_status`` row, skipping trusts where a snapshot task is already
pending. A trust that already has a record is never re-queued here — re-freezing would re-admit patients the
frozen membership excludes; ``POST /projects/{id}/cohort-snapshots`` handles a failed re-freeze per project.

Idempotent: a second run finds the first run's tasks pending and queues nothing more.

Usage (inside the running flip-api container):
    make -C flip-api backfill_cohort_snapshots
    make -C flip-api backfill_cohort_snapshots EXTRA_ARGS="--dry-run"
"""

import argparse
import json
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, col, select

from flip_api.db.database import get_engine
from flip_api.db.models.main_models import Projects
from flip_api.domain.interfaces.trust import ITrust
from flip_api.domain.schemas.status import CohortSnapshotState, ProjectStatus
from flip_api.project_services.services.cohort_snapshot_service import resolve_snapshot_states
from flip_api.project_services.services.project_services import get_approved_trusts_for_project
from flip_api.trusts_services.start_project_imaging_creation import queue_cohort_snapshot
from flip_api.utils.logger import logger


def backfill_cohort_snapshots(session: Session, dry_run: bool = False) -> list[dict[str, Any]]:
    """Queue PERSIST_COHORT at every approved trust of every APPROVED project with no snapshot record.

    Args:
        session (Session): Database session.
        dry_run (bool): Report what would be queued without queuing it.

    Returns:
        list[dict[str, Any]]: One entry per trust considered for queuing: project and trust ids, the trust name
        and the outcome (``queued``, ``would_queue`` or ``failed`` with the reason).
    """
    project_ids = session.exec(
        select(Projects.id).where(Projects.status == ProjectStatus.APPROVED).where(col(Projects.deleted).is_(False))
    ).all()

    outcomes: list[dict[str, Any]] = []
    for project_id in project_ids:
        trusts = get_approved_trusts_for_project(project_id, session)
        for entry in resolve_snapshot_states(project_id, trusts, session):
            if entry.record is not None or entry.state == CohortSnapshotState.PENDING:
                continue
            outcome: dict[str, Any] = {
                "project_id": str(project_id),
                "trust_id": str(entry.trust.id),
                "trust_name": entry.trust.name,
            }
            if dry_run:
                outcomes.append({**outcome, "outcome": "would_queue"})
                continue
            try:
                queue_cohort_snapshot(project_id, ITrust(id=entry.trust.id, name=entry.trust.name), session)
                outcomes.append({**outcome, "outcome": "queued"})
            except HTTPException as e:
                outcomes.append({**outcome, "outcome": "failed", "reason": str(e.detail)})
    return outcomes


def main() -> None:
    """CLI entry point: backfill the cohort snapshots, print one JSON summary to stdout."""
    parser = argparse.ArgumentParser(description="Queue missing approval-time cohort snapshots (FLIP#857).")
    parser.add_argument("--dry-run", action="store_true", help="List what would be queued; queue nothing.")
    args = parser.parse_args()

    with Session(get_engine()) as session:
        outcomes = backfill_cohort_snapshots(session, dry_run=args.dry_run)

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome["outcome"]] = counts.get(outcome["outcome"], 0) + 1
    logger.info(f"Cohort snapshot backfill: {counts or 'nothing to queue'}")
    print(json.dumps({"counts": counts, "trusts": outcomes}, indent=2))


if __name__ == "__main__":
    main()
