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

"""Create the dev object store's buckets, idempotently (FLIP#1291).

Run once by the ``object-store-init`` service in ``deploy/compose.development.yml`` after the RustFS
container is healthy and before flip-api and the fl-servers start. RustFS has no "default buckets"
setting, so this is the one-shot that stands in for it; it uses boto3's own env (``AWS_ENDPOINT_URL_S3``
and the static dev keys) exactly as the services do. ``BUCKETS`` is a comma-separated list of bucket
names. A bucket that already exists is fine; any other error is fatal so the stack does not come up
half-wired.
"""

import os
import sys

import boto3
from botocore.exceptions import ClientError

ALREADY_EXISTS = ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")


def bucket_names(raw: str) -> list[str]:
    """The distinct bucket names in a comma-separated list, in first-seen order, blanks dropped."""
    return list(dict.fromkeys(name.strip() for name in raw.split(",") if name.strip()))


def create_buckets(client, names: list[str]) -> list[str]:  # noqa: ANN001 — a boto3 S3 client (no stub)
    """Create every bucket in ``names`` that does not exist yet.

    Returns:
        list[str]: The buckets created by this call (existing ones are skipped, not listed).

    Raises:
        botocore.exceptions.ClientError: Any failure other than the bucket already existing.
    """
    created = []
    for name in names:
        try:
            client.create_bucket(Bucket=name)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ALREADY_EXISTS:
                raise
            print(f"object-store: bucket {name!r} already exists")
            continue
        created.append(name)
        print(f"object-store: created bucket {name!r}")
    return created


def main() -> int:
    """Entry point: ``BUCKETS`` from the environment, boto3 configured from its own env."""
    names = bucket_names(os.environ.get("BUCKETS", ""))
    if not names:
        print("object-store: BUCKETS is empty, nothing to create", file=sys.stderr)
        return 1
    create_buckets(boto3.client("s3"), names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
