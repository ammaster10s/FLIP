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

"""Unit tests for the approved-cohort snapshot file store (FLIP#857)."""

import json
import os
import time
import uuid
from typing import Any
from unittest.mock import patch

import pytest

from data_access_api.services import cohort_snapshot
from data_access_api.services.cohort_snapshot import (
    Snapshot,
    SnapshotStoreDisabled,
    SnapshotTooLarge,
    delete_snapshot,
    ensure_store,
    get_snapshot,
    normalised_query_hash,
    save_snapshot,
    snapshot_enabled,
)

PROJECT_ID = "8b2e9d6e-5a53-4f2e-9c37-2c8f4f0f2d11"
QUERY = "SELECT person_id, accession_id FROM omop.image_occurrence"


@pytest.fixture
def store(tmp_path):
    """A configured, writable snapshot store rooted in a per-test temp directory."""
    with patch("data_access_api.services.cohort_snapshot.get_settings") as mock_settings:
        mock_settings.return_value.COHORT_SNAPSHOT_DIR = str(tmp_path)
        mock_settings.return_value.SNAPSHOT_MAX_BYTES = 536_870_912
        yield tmp_path


def _save(project_id: str = PROJECT_ID, **overrides: Any) -> Snapshot:
    kwargs: dict[str, Any] = {
        "query": QUERY,
        "person_ids": ["1", "2", "3"],
        "accession_ids": ["A1", "A2", "A3"],
        "row_count": 3,
        "subject_count": 3,
        "columns": ["person_id", "accession_id"],
    }
    kwargs.update(overrides)
    return save_snapshot(project_id, **kwargs)


def test_save_then_get_round_trips_the_membership(store):
    saved = _save()

    snapshot = get_snapshot(PROJECT_ID)
    assert snapshot == saved
    assert snapshot.query == QUERY
    assert snapshot.query_hash == normalised_query_hash(QUERY)
    assert snapshot.person_ids == ("1", "2", "3")
    assert snapshot.accession_ids == ("A1", "A2", "A3")
    assert snapshot.has_accessions is True


def test_the_record_holds_ids_and_sql_only(store):
    """The artefact is a small, readable JSON file of identifiers — no clinical values."""
    _save()
    files = [p.name for p in (store / PROJECT_ID).iterdir()]
    assert files == ["membership.json"]
    record = json.loads((store / PROJECT_ID / "membership.json").read_text())
    assert set(record) == {
        "query",
        "query_hash",
        "person_ids",
        "accession_ids",
        "row_count",
        "subject_count",
        "columns",
        "created_at",
        "format_version",
    }


def test_save_overwrites_atomically_on_reapproval(store):
    _save()
    _save(query="SELECT person_id FROM omop.person", person_ids=["1", "2"], accession_ids=None, columns=["person_id"])

    snapshot = get_snapshot(PROJECT_ID)
    assert snapshot is not None
    assert snapshot.person_ids == ("1", "2")
    assert snapshot.has_accessions is False
    # No write debris left behind after the swap.
    leftovers = [p.name for p in store.iterdir() if p.name.startswith((".tmp-", ".old-"))]
    assert leftovers == []


def test_get_returns_none_for_unknown_project_and_non_uuid_ids(store):
    assert get_snapshot(str(uuid.uuid4())) is None
    # A non-UUID id must never touch the filesystem — it is a path component.
    assert get_snapshot("../../etc/passwd") is None
    assert get_snapshot("my_project") is None


def test_save_rejects_non_uuid_project_id(store):
    with pytest.raises(ValueError, match="UUID"):
        _save("../escape")
    assert list(store.iterdir()) == []


def test_save_refuses_oversized_snapshot_without_truncating(store):
    with patch("data_access_api.services.cohort_snapshot.get_settings") as mock_settings:
        mock_settings.return_value.COHORT_SNAPSHOT_DIR = str(store)
        mock_settings.return_value.SNAPSHOT_MAX_BYTES = 10
        with pytest.raises(SnapshotTooLarge, match="SNAPSHOT_MAX_BYTES"):
            _save()
    # Refused means nothing persisted — no partial membership that silently drops patients.
    assert get_snapshot(PROJECT_ID) is None


def test_disabled_store_reads_none_and_refuses_writes():
    with patch("data_access_api.services.cohort_snapshot.get_settings") as mock_settings:
        mock_settings.return_value.COHORT_SNAPSHOT_DIR = ""
        assert snapshot_enabled() is False
        assert get_snapshot(PROJECT_ID) is None
        assert delete_snapshot(PROJECT_ID) is False
        with pytest.raises(SnapshotStoreDisabled):
            _save()


def test_corrupt_meta_is_treated_as_absent(store):
    _save()
    (store / PROJECT_ID / "membership.json").write_text("{not json")
    assert get_snapshot(PROJECT_ID) is None


def test_unknown_format_version_is_treated_as_absent(store):
    _save()
    meta_path = store / PROJECT_ID / "membership.json"
    meta = json.loads(meta_path.read_text())
    meta["format_version"] = 999
    meta_path.write_text(json.dumps(meta))
    assert get_snapshot(PROJECT_ID) is None


def test_delete_is_idempotent(store):
    _save()
    assert delete_snapshot(PROJECT_ID) is True
    assert get_snapshot(PROJECT_ID) is None
    assert delete_snapshot(PROJECT_ID) is False


def test_ensure_store_sweeps_stale_write_debris(store):
    _save()
    _abandoned(store / ".tmp-crashed-write")
    _abandoned(store / ".old-crashed-swap")

    ensure_store()

    survivors = sorted(p.name for p in store.iterdir())
    assert survivors == [PROJECT_ID]
    assert get_snapshot(PROJECT_ID) is not None


def test_ensure_store_survives_unwritable_directory(tmp_path):
    target = tmp_path / "readonly"
    target.mkdir()
    target.chmod(0o500)
    try:
        with patch("data_access_api.services.cohort_snapshot.get_settings") as mock_settings:
            mock_settings.return_value.COHORT_SNAPSHOT_DIR = str(target)
            # Must log and return, never raise: a broken store cannot take OMOP serving down.
            ensure_store()
    finally:
        target.chmod(0o700)


def test_normalised_query_hash_ignores_case_and_whitespace_only():
    base = normalised_query_hash("SELECT * FROM omop.person")
    assert normalised_query_hash("  select *\n  FROM   omop.person  ") == base
    assert normalised_query_hash("SELECT person_id FROM omop.person") != base


def test_hash_key_matches_module_constant_shape():
    # cohort_snapshot deliberately does not import query_cache: pin that its normalisation
    # stays self-contained and deterministic.
    assert len(cohort_snapshot.normalised_query_hash("x")) == 64


@pytest.mark.parametrize(
    "overrides",
    [
        {"person_ids": None, "accession_ids": None},
        {"person_ids": "12345"},
        {"accession_ids": [1, 2]},
        {"row_count": -1},
        {"subject_count": True},
        {"query": "  "},
    ],
)
def test_a_malformed_membership_is_refused_on_construction(store, overrides):
    """Above all a record freezing no id column: it would leave the serving filter nothing to
    restrict by."""
    with pytest.raises(ValueError, match="membership|strings|integer"):
        _save(**overrides)
    assert get_snapshot(PROJECT_ID) is None


@pytest.mark.parametrize(
    "patch_record",
    [
        {"person_ids": None, "accession_ids": None},
        {"person_ids": "12345"},
        {"subject_count": "3"},
    ],
)
def test_a_malformed_record_on_disk_is_treated_as_absent(store, patch_record):
    _save()
    path = store / PROJECT_ID / "membership.json"
    record = json.loads(path.read_text())
    record.update(patch_record)
    path.write_text(json.dumps(record))
    assert get_snapshot(PROJECT_ID) is None


def test_the_record_cannot_be_mutated_in_memory(store):
    snapshot = _save()
    assert isinstance(snapshot.person_ids, tuple)
    assert isinstance(snapshot.columns, tuple)


def test_a_failed_replace_keeps_the_previous_membership(store):
    """Re-approval must never destroy the last good record: if the new record cannot be moved
    into place, the superseded one is put back."""
    _save()
    real_replace = cohort_snapshot.os.replace

    def fail_activation(src, dst):
        if str(src).rsplit("/", 1)[-1].startswith(".tmp-"):
            raise OSError("disk full")
        return real_replace(src, dst)

    with patch("data_access_api.services.cohort_snapshot.os.replace", side_effect=fail_activation):
        with pytest.raises(OSError, match="disk full"):
            _save(person_ids=["9"], accession_ids=None, columns=["person_id"])

    snapshot = get_snapshot(PROJECT_ID)
    assert snapshot is not None
    assert snapshot.person_ids == ("1", "2", "3")
    assert [p.name for p in store.iterdir()] == [PROJECT_ID]


def test_ensure_store_restores_a_superseded_record_orphaned_by_a_crash(store):
    """A crash between the two renames leaves the last good record under ``.old-``: restore it."""
    _save()
    (store / PROJECT_ID).rename(store / f".old-{PROJECT_ID}-deadbeef")
    _age(store / f".old-{PROJECT_ID}-deadbeef")

    ensure_store()

    assert get_snapshot(PROJECT_ID) is not None
    assert sorted(p.name for p in store.iterdir()) == [PROJECT_ID]


def test_ensure_store_never_restores_a_deletion(store):
    """A crash mid-delete must not resurrect the record: deletion tombstones are only swept."""
    _save()
    (store / PROJECT_ID).rename(store / f".del-{PROJECT_ID}-deadbeef")
    _age(store / f".del-{PROJECT_ID}-deadbeef")

    ensure_store()

    assert get_snapshot(PROJECT_ID) is None
    assert list(store.iterdir()) == []


def test_ensure_store_leaves_a_write_in_flight_alone(store):
    """On a shared (ReadWriteMany) store another replica may be mid-write while this one boots:
    only debris old enough to have been abandoned is swept or restored."""
    _save()
    (store / PROJECT_ID).rename(store / f".old-{PROJECT_ID}-cafef00d")
    (store / f".tmp-{PROJECT_ID}-cafef00d").mkdir()

    ensure_store()

    assert sorted(p.name for p in store.iterdir()) == [f".old-{PROJECT_ID}-cafef00d", f".tmp-{PROJECT_ID}-cafef00d"]


def _age(path, seconds: int = 3600) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


def _abandoned(path) -> None:
    path.mkdir()
    _age(path)
