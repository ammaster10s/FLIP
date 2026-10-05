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

from urllib.parse import quote


def quote_path_segment(value: str) -> str:
    """Quote one XNAT identifier, rejecting segments that cannot identify a resource.

    Args:
        value (str): The raw identifier or filename, not an already-encoded URL segment.

    Returns:
        str: The identifier encoded as one URL path segment.

    Raises:
        ValueError: If the identifier is empty or a dot-segment. ``quote`` leaves literal
            dots unchanged, allowing HTTP clients to normalize ``.`` or ``..`` away.
    """
    if not value or value in (".", ".."):
        raise ValueError("XNAT path segment must not be empty or a dot-segment")
    return quote(value, safe="")
