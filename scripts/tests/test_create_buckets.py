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

"""The dev object store's bucket bootstrap, ``deploy/object-store/create_buckets.py`` (FLIP#1291)."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "object-store" / "create_buckets.py"


@pytest.fixture(scope="module")
def create_buckets_module():
    spec = importlib.util.spec_from_file_location("create_buckets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["create_buckets"] = module
    spec.loader.exec_module(module)
    return module


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "CreateBucket")


def test_bucket_names_dedupes_and_drops_blanks(create_buckets_module):
    assert create_buckets_module.bucket_names(" a, b ,,a,") == ["a", "b"]
    assert create_buckets_module.bucket_names("") == []


def test_create_buckets_skips_existing_and_creates_the_rest(create_buckets_module):
    """Idempotent: a second `make up` finds the buckets already there and creates nothing."""
    client = MagicMock()
    client.create_bucket.side_effect = [_client_error("BucketAlreadyOwnedByYou"), None]

    created = create_buckets_module.create_buckets(client, ["existing", "new"])

    assert created == ["new"]
    assert [call.kwargs["Bucket"] for call in client.create_bucket.call_args_list] == ["existing", "new"]


def test_create_buckets_raises_on_any_other_error(create_buckets_module):
    """A store that refuses (bad credentials, not up) must fail the init service, not come up half-wired."""
    client = MagicMock()
    client.create_bucket.side_effect = _client_error("InvalidAccessKeyId")

    with pytest.raises(ClientError):
        create_buckets_module.create_buckets(client, ["bucket"])


def test_main_refuses_an_empty_bucket_list(create_buckets_module, monkeypatch):
    monkeypatch.setenv("BUCKETS", " , ")
    assert create_buckets_module.main() == 1


def test_main_creates_the_listed_buckets_through_a_vanilla_client(create_buckets_module, monkeypatch):
    """boto3 is configured from its own env (endpoint + static keys), exactly as the services are."""
    client = MagicMock()
    monkeypatch.setenv("BUCKETS", "flip-model-files,flip-fl-results")
    monkeypatch.setattr(create_buckets_module.boto3, "client", lambda service: client if service == "s3" else None)

    assert create_buckets_module.main() == 0
    assert [call.kwargs["Bucket"] for call in client.create_bucket.call_args_list] == [
        "flip-model-files",
        "flip-fl-results",
    ]
