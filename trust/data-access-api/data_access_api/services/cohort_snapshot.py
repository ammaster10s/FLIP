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

"""Durable, project-keyed store for the approved-cohort MEMBERSHIP (FLIP#857).

At project approval the trust runs its cohort query once and records who is in it: the query of
record plus the ``person_id`` and/or ``accession_id`` values it returned. The row-level routes then
re-run that stored query (never the caller's SQL) and keep only rows whose ids are in the frozen
set, so an approved cohort can SHRINK — a patient removed from OMOP (an opt-out, a correction) drops
out and their data is no longer reachable — but can never GROW with the live database.

What is stored is identifiers and the SQL text, never clinical values: the artefact is a small,
human-readable JSON file an operator can inspect, diff and audit, and the attribute data stays in
OMOP where the trust's existing governance applies to it. Deliberately a file store: data-access-api
keeps zero write access to any database, and researcher SQL (pinned to the ``omop`` schema by
``validate_query``) cannot reach a filesystem at all.

Layout, one file per hub project id::

    <COHORT_SNAPSHOT_DIR>/<project-uuid>/membership.json

Writes are atomic at directory granularity: the file lands in a ``.tmp-*`` sibling first and is
activated with ``os.replace`` renames, so a reader never observes a half-written record and a crash
mid-write leaves (at worst) a stale temp directory that the boot-time sweep removes. There is no TTL
and no in-place mutation — a record is replaced by a re-approval or deleted, never edited.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from data_access_api.config import get_settings
from data_access_api.utils.logger import logger

# Bumped when the on-disk layout changes; a record with an unknown version is treated as absent
# (the project refuses row-level serving until it is re-approved) rather than mis-read.
_FORMAT_VERSION = 2
_MEMBERSHIP_FILENAME = "membership.json"
# Work-in-progress / superseded directories. Never valid records; swept at startup.
_TMP_PREFIX = ".tmp-"
_OLD_PREFIX = ".old-"
# A record being deleted. Unlike a superseded one, never restored: the deletion wins.
_DEL_PREFIX = ".del-"


class SnapshotStoreDisabled(Exception):
    """Raised on writes when ``COHORT_SNAPSHOT_DIR`` is not configured."""


class SnapshotTooLarge(Exception):
    """Raised when the serialized record exceeds ``SNAPSHOT_MAX_BYTES`` (never truncated)."""


@dataclass(frozen=True)
class Snapshot:
    """A project's frozen cohort membership.

    Validated on construction, so a record read back from disk that is malformed — above all one
    that freezes no id column, which would leave the serving filter nothing to restrict by — raises
    and is treated as absent rather than served. The sequences are stored as tuples, so the frozen
    record cannot be mutated in memory.
    """

    # The raw SQL of record, re-run (through validate_query) on every row-level fetch.
    query: str
    query_hash: str
    # The frozen member ids, as strings. None when the cohort does not project that column.
    # Serving keeps a row only if every frozen column's value is in its set, so neither a new
    # patient nor a new study of an existing patient can enter an approved cohort.
    person_ids: Sequence[str] | None
    accession_ids: Sequence[str] | None
    # Facts at approval, for the hub's audit strip and drift check. Serving re-counts live.
    row_count: int
    subject_count: int
    columns: Sequence[str]
    created_at: str  # ISO-8601 UTC
    format_version: int = _FORMAT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("a cohort membership needs its query of record")
        if self.person_ids is None and self.accession_ids is None:
            raise ValueError("a cohort membership must freeze person_ids, accession_ids or both")
        for name in ("person_ids", "accession_ids", "columns"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, str) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be a list of strings")
            object.__setattr__(self, name, tuple(value))
        for name in ("row_count", "subject_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def has_accessions(self) -> bool:
        return self.accession_ids is not None


def normalised_query_hash(query: str) -> str:
    """SHA-256 of the whitespace-normalised, lowercased SQL text.

    Used only to *detect and log* when a caller-supplied query differs from the one of record —
    never as a security control (the stored query is served either way; that is the point).
    Hashes the raw submitted text, not the validator's re-emitted form, so the hub-side string of
    record compares equal across submission and serving.
    """
    normalised = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()


def snapshot_enabled() -> bool:
    """Whether a snapshot directory is configured (empty ``COHORT_SNAPSHOT_DIR`` = disabled)."""
    return bool(get_settings().COHORT_SNAPSHOT_DIR)


def _store_dir() -> Path:
    configured = get_settings().COHORT_SNAPSHOT_DIR
    if not configured:
        raise SnapshotStoreDisabled("COHORT_SNAPSHOT_DIR is not configured")
    return Path(configured)


def _canonical_project_id(project_id: str) -> str | None:
    """The project id as a canonical UUID string, or None when it is not a UUID.

    The id becomes a directory name, so only a parsed-and-re-emitted UUID is ever used as
    a path component — nothing else reaches the filesystem (no traversal surface, even
    though every caller is already authenticated and the id is hub-encrypted).
    """
    try:
        return str(uuid.UUID(str(project_id)))
    except (ValueError, AttributeError, TypeError):
        return None


def _project_key_of(work_dir_name: str, prefix: str) -> str:
    """The project UUID a ``<prefix><uuid>-<nonce>`` work directory belongs to."""
    return work_dir_name[len(prefix) :].rsplit("-", 1)[0]


def ensure_store() -> None:
    """Boot-time store check: create the directory, sweep stale temp dirs, probe writability.

    Never raises — a missing or unwritable store must not take the service (and the
    statistics route) down. Failures log at ERROR with the remediation; every subsequent
    write fails loudly per-call and every read returns None, which the row-level routes
    refuse (fail-closed).
    """
    if not snapshot_enabled():
        logger.error(
            "Cohort snapshot store DISABLED (COHORT_SNAPSHOT_DIR unset): snapshots cannot be "
            "created and the row-level routes will refuse every project (fail-closed). Set "
            "COHORT_SNAPSHOT_DIR / mount the snapshot volume."
        )
        return

    base = _store_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
        # Sweep leftovers from crashed writes: only this service writes here, and no write
        # can be in flight during startup. A superseded record whose replacement never landed
        # (a crash between the two renames) is the project's last good membership: restore it.
        for stale in sorted(base.iterdir(), key=lambda path: path.name):
            if stale.name.startswith(_OLD_PREFIX):
                project_key = _canonical_project_id(_project_key_of(stale.name, _OLD_PREFIX))
                active = base / project_key if project_key else None
                if active is not None and not active.exists():
                    os.replace(stale, active)
                    logger.warning(f"Restored superseded cohort membership for project {active.name}")
                    continue
            if stale.name.startswith((_TMP_PREFIX, _OLD_PREFIX, _DEL_PREFIX)):
                shutil.rmtree(stale, ignore_errors=True)
                logger.warning(f"Removed stale snapshot work directory {stale.name}")
        probe = base / f"{_TMP_PREFIX}write-probe"
        probe.mkdir(exist_ok=True)
        probe.rmdir()
    except OSError:
        logger.exception(
            f"Cohort snapshot store at {base} is not writable — snapshots cannot be created and "
            "the row-level routes will refuse projects whose artefact cannot be read (fail-closed). "
            f"Remediation: create the directory on the host and chown it to this service's uid "
            f"(uid {os.getuid()})."
        )
        return

    logger.info(f"Cohort snapshot store ready at {base}")


def save_snapshot(
    project_id: str,
    query: str,
    person_ids: Sequence[str] | None,
    accession_ids: Sequence[str] | None,
    row_count: int,
    subject_count: int,
    columns: Sequence[str],
) -> Snapshot:
    """Persist the cohort membership for ``project_id``, atomically replacing any predecessor.

    Args:
        project_id (str): The decrypted hub project id (must be a UUID).
        query (str): The raw SQL of record.
        person_ids (Sequence[str] | None): The frozen ``person_id`` values, or None when not projected.
        accession_ids (Sequence[str] | None): The frozen ``accession_id`` values, or None when not projected.
        row_count (int): Rows the query returned at approval.
        subject_count (int): Distinct subjects at approval, as ``count_distinct_subjects`` took them.
        columns (Sequence[str]): The query's column names at approval.

    Returns:
        Snapshot: What was written.

    Raises:
        SnapshotStoreDisabled: When no store directory is configured.
        SnapshotTooLarge: When the serialized record exceeds ``SNAPSHOT_MAX_BYTES``.
        ValueError: When ``project_id`` is not a UUID, or the membership is malformed (no id column).
        OSError: When the store directory is not writable.
    """
    base = _store_dir()
    canonical = _canonical_project_id(project_id)
    if canonical is None:
        raise ValueError("project_id must be a UUID to key a cohort snapshot")

    snapshot = Snapshot(
        query=query,
        query_hash=normalised_query_hash(query),
        person_ids=person_ids,
        accession_ids=accession_ids,
        row_count=row_count,
        subject_count=subject_count,
        columns=columns,
        created_at=datetime.now(UTC).isoformat(),
    )
    payload = json.dumps(asdict(snapshot), indent=1).encode()

    max_bytes = get_settings().SNAPSHOT_MAX_BYTES
    if len(payload) > max_bytes:
        # Refuse rather than truncate: a partial membership silently drops patients from training.
        raise SnapshotTooLarge(
            f"Serialized cohort membership is {len(payload)} bytes, over the {max_bytes}-byte limit "
            "(SNAPSHOT_MAX_BYTES). Raise the limit."
        )

    base.mkdir(parents=True, exist_ok=True)
    nonce = uuid.uuid4().hex[:8]
    workdir = base / f"{_TMP_PREFIX}{canonical}-{nonce}"
    final = base / canonical
    superseded = base / f"{_OLD_PREFIX}{canonical}-{nonce}"
    try:
        workdir.mkdir()
        with open(workdir / _MEMBERSHIP_FILENAME, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # Two atomic renames. A reader sees the old record or the new one, never a half-written
        # one. If the second rename fails the old record is put back; if the process dies between
        # them, the boot sweep restores it.
        if final.exists():
            os.replace(final, superseded)
        try:
            os.replace(workdir, final)
        except OSError:
            if superseded.exists() and not final.exists():
                os.replace(superseded, final)
            raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(superseded, ignore_errors=True)

    logger.info(
        f"Cohort membership saved for project {canonical}: {len(person_ids or [])} person ids, "
        f"{len(accession_ids or [])} accession ids, {len(payload)} bytes"
    )
    return snapshot


def get_snapshot(project_id: str) -> Snapshot | None:
    """The frozen membership for ``project_id``, or None when there is none to serve.

    None covers every no-record case — store disabled, non-UUID project id, not approved yet,
    unreadable/corrupt/unknown-version record (logged at ERROR). The row-level routes refuse on
    None (fail-closed).
    """
    if not snapshot_enabled():
        return None
    canonical = _canonical_project_id(project_id)
    if canonical is None:
        logger.debug(f"Project id {project_id!r} is not a UUID; no snapshot lookup")
        return None

    path = _store_dir() / canonical / _MEMBERSHIP_FILENAME
    try:
        if not path.exists():
            return None
        raw = json.loads(path.read_text())
        if raw.get("format_version") != _FORMAT_VERSION:
            logger.error(
                f"Cohort membership for project {canonical} has format_version "
                f"{raw.get('format_version')} (expected {_FORMAT_VERSION}) — treating as absent"
            )
            return None
        return Snapshot(**raw)
    except Exception:
        logger.exception(
            f"Cohort membership for project {canonical} is unreadable — treating as absent "
            "(row-level routes refuse the project)"
        )
        return None


def delete_snapshot(project_id: str) -> bool:
    """Remove the snapshot for ``project_id``. Idempotent; True if one existed."""
    if not snapshot_enabled():
        return False
    canonical = _canonical_project_id(project_id)
    if canonical is None:
        return False

    snapshot_dir = _store_dir() / canonical
    if not snapshot_dir.exists():
        return False
    # Move aside first so a concurrent reader sees either the intact snapshot or none —
    # never a directory whose files are vanishing under it mid-read.
    tomb = _store_dir() / f"{_DEL_PREFIX}{canonical}-{uuid.uuid4().hex[:8]}"
    os.replace(snapshot_dir, tomb)
    shutil.rmtree(tomb, ignore_errors=True)
    logger.info(f"Cohort snapshot deleted for project {canonical}")
    return True
