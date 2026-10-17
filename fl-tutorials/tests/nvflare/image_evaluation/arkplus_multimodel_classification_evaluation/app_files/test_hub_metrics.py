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

"""The Ark+ multimodel evaluation sends only per-model, per-lesion AUROC to the hub (FLIP#1526).

The evaluator's real replies (``compute_metrics``, AUROC plus the DeLong maps) go through FLIP's
``EvaluationJsonGenerator`` with the app's own ``config.json`` ``HUB_METRICS_EXCLUDE``.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import numpy as np
from flip.nvflare.components.evaluation_json_generator import HUB_METRICS_EXCLUDE_KEY, EvaluationJsonGenerator
from nvflare.apis.dxo import DXO, DataKind
from nvflare.app_common.app_constant import AppConstants
from nvflare.app_common.app_event_type import AppEventType
from tutorial_apps import TUTORIALS_ROOT, load_module

APP_FILES = TUTORIALS_ROOT / "nvflare/image_evaluation/arkplus_multimodel_classification_evaluation/app_files"


def _evaluator():
    """Import the evaluator; its flat sibling imports need ``app_files/`` on ``sys.path``.

    The siblings (``data_utils``, ``models``, ...) are dropped from ``sys.modules`` afterwards so another
    app's same-named module is never served from this one's cache.
    """
    before = set(sys.modules)
    sys.path.insert(0, str(APP_FILES))
    try:
        return load_module("fl_tutorials_under_test.arkplus_multimodel_evaluator", APP_FILES / "evaluator.py")
    finally:
        sys.path.remove(str(APP_FILES))
        for name in set(sys.modules) - before:
            if (getattr(sys.modules[name], "__file__", None) or "").startswith(str(APP_FILES)):
                del sys.modules[name]


def _receive(generator: EvaluationJsonGenerator, client: str, owner: str, metrics: dict) -> None:
    props = {
        AppConstants.DATA_CLIENT: client,
        AppConstants.MODEL_OWNER: owner,
        AppConstants.VALIDATION_RESULT: DXO(data_kind=DataKind.METRICS, data=metrics).to_shareable(),
    }
    fl_ctx = MagicMock()
    fl_ctx.get_prop.side_effect = lambda key, default=None: props.get(key, default)
    generator.handle_evaluation_events(AppEventType.VALIDATION_RESULT_RECEIVED, fl_ctx)


def test_hub_gets_exactly_one_auroc_per_model_per_lesion():
    evaluator = _evaluator()
    config = json.loads((APP_FILES / "config.json").read_text())
    models = list(config["models"])
    lesions = [(int(k), v) for k, v in config["LESIONS"].items() if int(k) >= 0]

    rng = np.random.default_rng(0)
    targets = np.tile(np.eye(len(lesions)), (8, 1))
    predictions = {m: rng.random(targets.shape) for m in models}
    all_targets = {m: targets for m in models}

    generator = EvaluationJsonGenerator()
    # As on a trust: one validate task per model, each reply carrying every model scored so far.
    for scored in range(1, len(models) + 1):
        reply = evaluator.compute_metrics(models[:scored], predictions, all_targets, lesions)
        _receive(generator, "Trust_1", f"SRV_{models[scored - 1]}", reply)

    labels = generator.hub_metrics(exclude=config[HUB_METRICS_EXCLUDE_KEY])["Trust_1"]

    assert sorted(labels) == sorted(f"{m}/AUROC_{lesion}".upper() for m in models for _, lesion in lesions)
    assert len(labels) == 10
    # The downloaded results keep the DeLong maps.
    assert "delong_p_values" in generator._eval_results["Trust_1"][f"SRV_{models[-1]}"][models[0]]
