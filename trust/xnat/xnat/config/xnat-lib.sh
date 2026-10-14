#!/bin/bash
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

# Helpers shared by configure-xnat.sh, configure-dcm2niix.sh and wait-for-xnat-plugins.sh, which
# source this file from their own directory. It defines functions only. Credentials always travel
# in the caller's arguments: configure-xnat.sh changes admin password part-way through a run.

# Prints its arguments with the value after -u (credentials) or -d/--data-binary (payloads carry the
# admin and service passwords) replaced, so a failure never writes them to the tee'd configure log.
scrub_args() {
  local redact_next=""
  local arg
  local out=""
  for arg in "$@"; do
    if [[ -n "$redact_next" ]]; then
      out+=" <redacted>"
      redact_next=""
    elif [[ "$arg" == "-u" || "$arg" == "-d" || "$arg" == "--data-binary" ]]; then
      out+=" $arg"
      redact_next=1
    else
      out+=" $arg"
    fi
  done
  printf '%s' "${out# }"
}

# One request to XNAT that never fails on its HTTP status, for callers that read the status
# themselves. Sets xnat_status (000 when nothing answered: refused or timed out) and xnat_body.
# usage: xnat_request <connect timeout s> <max time s> <curl args>
xnat_request() {
  local connect_timeout=$1 max_time=$2 response
  shift 2
  response=$(curl -sS --connect-timeout "$connect_timeout" --max-time "$max_time" -w '\n%{http_code}' "$@") \
    || response=$'\n000'
  # shellcheck disable=SC2034  # the caller reads them
  xnat_status=${response##*$'\n'} xnat_body=${response%$'\n'*}
}

# curl wrapper for XNAT's REST API. On 2xx, prints the response body. On any other status, or a curl
# transport failure, reports the request (and, for HTTP failures, the body) on stderr and returns
# non-zero, which `set -e` turns into an abort at the call site. Bare `curl -s` exits 0 on HTTP
# errors, which is how a rejected configuration call once skipped its step invisibly (FLIP#822,
# FLIP#862). --allow-not-modified as the first argument also accepts a 304, which DQR answers to a
# PUT of an availability interval that already matches.
xnat_curl() {
  local response
  local status
  local body
  local curl_exit=0
  local accepted='^2[0-9]{2}$'
  if [[ "${1:-}" == "--allow-not-modified" ]]; then
    accepted='^(2[0-9]{2}|304)$'
    shift
  fi
  response=$(curl -sS --connect-timeout 10 --max-time 120 -w '\n%{http_code}' "$@") || curl_exit=$?
  if [[ "$curl_exit" -ne 0 ]]; then
    echo "ERROR: curl transport failure (exit $curl_exit)" >&2
    echo "  args: $(scrub_args "$@")" >&2
    return 1
  fi
  status=$(printf '%s' "$response" | tail -n1)
  body=$(printf '%s' "$response" | sed '$d')
  # Strip CRs so a middlebox emitting \r\n line endings can't make the
  # callers' guards fail on an invisible character (a raw CR is not valid
  # inside JSON strings, so this is lossless).
  status=${status//$'\r'/}
  body=${body//$'\r'/}
  # Fail closed: anything other than a literal 2xx status line (including
  # an empty or non-numeric one) is an error, apart from the opted-in 304.
  if ! [[ "$status" =~ $accepted ]]; then
    echo "ERROR: XNAT request failed with HTTP $status" >&2
    echo "  args: $(scrub_args "$@")" >&2
    echo "  body: $body" >&2
    return 1
  fi
  if [[ -n "$body" ]]; then
    printf '%s\n' "$body"
  fi
}

# Waits until XNAT serves its login page, bounded in wall-clock time with a timeout on each probe,
# so a dead or wedged XNAT fails the run loudly instead of printing dots forever.
# usage: wait_for_xnat <seconds>
wait_for_xnat() {
  local wait_start=$SECONDS
  echo "Waiting for XNAT to be available..."
  until curl --output /dev/null --silent --head --fail \
    --connect-timeout 5 --max-time 10 "$XNAT_URL/app/template/Login.vm"; do
    if (( SECONDS - wait_start >= $1 )); then
      echo "ERROR: XNAT did not become available within $((SECONDS - wait_start))s" >&2
      exit 1
    fi
    printf '.'
    sleep 1
  done
  echo "XNAT is up!"
}

# An id XNAT returns goes into a URL. XNAT generates it, but check it is a plain number before using it.
require_numeric_id() {  # require_numeric_id <what XNAT returned> <id>
  [[ "$2" =~ ^[0-9]+$ ]] && return
  echo "ERROR: $1 with id '$2'" >&2
  exit 1
}
