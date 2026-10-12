#!/usr/bin/env bash
#
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
# Run one Flower tutorial on the standalone compose stack (fl-services/flower):
# bring up SuperLink + 2 SuperNodes + fl-api with the tutorial's dev data mounted,
# submit the job to the fl-api control plane, wait for it to finish (or fail), and
# tear down. Called by fl-tutorials/flower/Makefile's stack-tutorial. The release check and
# `run-tutorial` / `run-all-tutorials` use the simulator (sim-tutorial.sh), as on NVFLARE; this
# is the optional check of the deployment wiring the simulator skips (fl-api submit, SuperNode
# registration, the FL images).
#
# The run uses the tutorial's own pyproject.toml values, as sim-tutorial.sh does: fl-api's
# /submit_tutorial leaves out app/config.toml, which carries the platform settings (FLIP#1432).
# The SuperNodes get the GPU overlay (fl-services/flower/compose.dev.gpu.yml) when nvidia-smi
# sees a GPU; STACK_TUTORIAL_GPU=0 keeps the CPU, =1 forces the overlay.
# Exit 0 means the run FINISHED. FAILED, STOPPED, a SuperNode that is not running, fl-api
# polls failing for a minute, or no terminal status within WAIT_SECS (default 3600) exit 1,
# so run-all-tutorials never counts an unfinished tutorial as a pass.
set -euo pipefail

TUTORIAL="${1:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
COMPOSE_FILES="-f $REPO_ROOT/fl-services/flower/compose.dev.yml"
# The SuperNodes train on the GPU when the host has one (both reserve the same device, where
# sim-tutorial.sh gives each simulated site a fraction of it). STACK_TUTORIAL_GPU=0 keeps the CPU;
# =1 adds the overlay even where nvidia-smi is missing, and `compose up` then fails loudly.
case "${STACK_TUTORIAL_GPU:-auto}" in
  0|false|no) GPU=off ;;
  auto) if nvidia-smi -L >/dev/null 2>&1; then GPU=on; else GPU=off; fi ;;
  *) GPU=on ;;
esac
if [ "$GPU" = on ]; then COMPOSE_FILES="$COMPOSE_FILES -f $REPO_ROOT/fl-services/flower/compose.dev.gpu.yml"; fi
COMPOSE="docker compose $COMPOSE_FILES -p flwr"
WAIT_SECS="${WAIT_SECS:-3600}"

list() { for d in "$HERE"/*/app; do basename "$(dirname "$d")"; done; }
if [ -z "$TUTORIAL" ]; then echo "Set TUTORIAL=<name>. Available:"; list | sed 's/^/  - /'; exit 1; fi
if [ ! -d "$HERE/$TUTORIAL/app" ]; then echo "❌ Unknown tutorial '$TUTORIAL'. Available:"; list | sed 's/^/  - /'; exit 1; fi

# Per-tutorial dev data (LOCAL_DEV reads DEV_IMAGES_DIR / DEV_DATAFRAME), served from the
# shared gitignored fl-tutorials/data/ root (see fl-tutorials/datasets/). Every tutorial
# needs its dataset downloaded first.
DATA_ROOT="$(cd "$HERE/.." && pwd)/data"
case "$TUTORIAL" in
  3d_spleen_segmentation|3d_spleen_segmentation_evaluation)
    # The MSD build both backends read, honouring NUM_CASES.
    export DEV_IMAGES_DIR="$DATA_ROOT/spleen/images"
    export DEV_DATAFRAME="$DATA_ROOT/spleen/dataframe.csv"
    DATASET_TARGET=download-spleen-data ;;
  xray_classification)
    export DEV_IMAGES_DIR="$DATA_ROOT/xrays_mini_300/accession-resources"
    export DEV_DATAFRAME="$DATA_ROOT/xrays_mini_300/dataframe.csv"
    DATASET_TARGET=download-xray-data ;;
  ehr_risk_prediction)
    # Tabular-only tutorial: no images, so DEV_IMAGES_DIR stays unset — the compose default
    # (an empty images dir the app never reads) is fine. Both SuperNodes get the same CSV; each
    # ClientApp slices out its own person_id-modulo partition.
    export DEV_DATAFRAME="$DATA_ROOT/synthea/dataframe.csv"
    DATASET_TARGET=download-synthea-data ;;
  3d_prostate_segmentation)
    # The XNAT-export-shaped tree prepare_prostate_local_data.py writes from the PI-CAI download
    # (three scans per study, masks beside each), honouring NUM_CASES.
    export DEV_IMAGES_DIR="$DATA_ROOT/prostate/images"
    export DEV_DATAFRAME="$DATA_ROOT/prostate/dataframe.csv"
    DATASET_TARGET=prepare-prostate-local-data ;;
  *) echo "❌ No data mapping for '$TUTORIAL'"; exit 1 ;;
esac
if [ -n "${DEV_IMAGES_DIR:-}" ] && [ ! -d "$DEV_IMAGES_DIR" ]; then
  echo "❌ Dataset missing: $DEV_IMAGES_DIR"
  echo "   Run: make -C $REPO_ROOT/fl-tutorials $DATASET_TARGET"
  exit 1
fi
if [ -n "${DEV_DATAFRAME:-}" ] && [ ! -f "$DEV_DATAFRAME" ]; then
  echo "❌ Dataset missing: $DEV_DATAFRAME"
  echo "   Run: make -C $REPO_ROOT/fl-tutorials $DATASET_TARGET"
  exit 1
fi

export DOCKER_GID="$(id -g)"
export WORKING_DIR="$REPO_ROOT/fl-services/flower/runs"
mkdir -p "$WORKING_DIR" && chmod 777 "$WORKING_DIR"

cleanup() { echo "🧹 Tearing down..."; $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "🚀 Flower tutorial '$TUTORIAL' — starting standalone stack (GPU: $GPU)..."
$COMPOSE up -d --remove-orphans

echo "⏳ Waiting for fl-api health..."
healthy=false
for _ in $(seq 1 30); do
  $COMPOSE exec -T fl-api python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=3)" >/dev/null 2>&1 && { healthy=true; break; }
  sleep 2
done
# Fail fast if fl-api never came up: submitting against an unhealthy control plane
# just produces a confusing submit error (or a hang). This is an infra-precondition
# failure, distinct from the slow-but-fine training timeout handled below.
if [ "$healthy" != true ]; then
  echo "❌ fl-api did not become healthy within ~60s — aborting before submit."
  $COMPOSE logs fl-api 2>&1 | tail -20
  exit 1
fi

# A SuperNode that exited (e.g. a CUDA/driver mismatch once the GPU is reserved) would leave the
# run PENDING until WAIT_SECS and read as a slow host, so its absence fails the run with its logs.
check_supernodes() {
  local running
  running="$($COMPOSE ps --status running --services 2>/dev/null || true)"
  for sn in supernode-1 supernode-2; do
    if ! grep -qx "$sn" <<<"$running"; then
      echo "❌ $sn is not running:"; $COMPOSE logs "$sn" 2>&1 | tail -20; exit 1
    fi
  done
}
check_supernodes

echo "📤 Submitting '$TUTORIAL' to fl-api..."
# Tutorials submit by NAME via /submit_tutorial; /submit_run is UUID-only (flip-api's
# production model_id path), so posting a tutorial name there 422s. An HTTP error prints
# fl-api's detail (the flwr error), which urllib's own traceback leaves out.
RUN_ID="$($COMPOSE exec -T fl-api python -c "
import sys, urllib.error, urllib.request as u
try:
    print(u.urlopen(u.Request('http://localhost:8000/submit_tutorial/$TUTORIAL', method='POST')).read().decode())
except urllib.error.HTTPError as e:
    sys.exit(f'submit failed: HTTP {e.code}: {e.read().decode()}')")"
echo "   run id: $RUN_ID"

echo "⏳ Waiting up to ${WAIT_SECS}s for the run to reach a terminal status (polling fl-api /list_runs)..."
run_id_clean="$(printf '%s' "$RUN_ID" | tr -d '"[:space:]')"
deadline=$(( $(date +%s) + WAIT_SECS ))
last=""
pollerrs=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  # /list_runs returns [{job_id, status}] with normalized JobStatus (PENDING/RUNNING/
  # FINISHED/FAILED/STOPPED). Match our run and act on terminal states. A poll that fails
  # prints why; a minute of them in a row means fl-api is gone, not that the run is slow.
  st="$($COMPOSE exec -T fl-api python -c "
import urllib.request as u, json
try:
    runs = json.loads(u.urlopen('http://localhost:8000/list_runs', timeout=5).read())
    print(next((r['status'] for r in runs if str(r['job_id']) == '$run_id_clean'), 'UNKNOWN'))
except Exception as e:
    print(f'POLLERR {e!r}')" 2>&1 || echo "POLLERR fl-api exec failed")"
  [ "$st" != "$last" ] && { echo "   status: $st"; last="$st"; }
  if [[ "$st" == POLLERR* ]]; then
    pollerrs=$((pollerrs + 1))
    if [ "$pollerrs" -ge 12 ]; then echo "❌ '$TUTORIAL': fl-api /list_runs failed 12 times in a row"; exit 1; fi
  else
    pollerrs=0
  fi
  check_supernodes
  case "$st" in
    FINISHED) echo "✅ '$TUTORIAL' run FINISHED"; exit 0 ;;
    FAILED)   echo "❌ '$TUTORIAL' run FAILED"; $COMPOSE logs supernode-1 2>&1 | tail -15; exit 1 ;;
    STOPPED)  echo "❌ '$TUTORIAL' run STOPPED before it finished"; exit 1 ;;
  esac
  sleep 5
done
rounds="$($COMPOSE logs supernode-1 2>&1 | grep -c 'Push .AppOutputs.' || true)"
echo "❌ '$TUTORIAL' not terminal within ${WAIT_SECS}s (last status: ${last:-unknown}, ${rounds} ClientApp round(s) done). Increase WAIT_SECS for a slow host."
exit 1
