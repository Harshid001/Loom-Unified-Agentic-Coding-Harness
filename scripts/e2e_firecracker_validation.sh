#!/usr/bin/env bash
set -euo pipefail

WORKER_URL="${LOOM_FIRECRACKER_WORKER_URL:-http://127.0.0.1:8101}"
TOKEN="${LOOM_FIRECRACKER_WORKER_TOKEN:?LOOM_FIRECRACKER_WORKER_TOKEN is required}"
REPO_PATH="${LOOM_FIRECRACKER_TEST_REPO:-/var/repos/loom-firecracker-test}"
CANARY="${LOOM_FIRECRACKER_CANARY:-HOST_SECRET_DO_NOT_LEAK}"
HOST_CANARY_PATH="${LOOM_FIRECRACKER_HOST_CANARY_PATH:-/tmp/loom-secret-test}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; rm -f "$HOST_CANARY_PATH"' EXIT
printf '%s\n' "$CANARY" > "$HOST_CANARY_PATH"

curl_json() {
  curl --fail-with-body --silent --show-error \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' "$@"
}

printf 'FIRECRACKER END-TO-END VALIDATION\n----------------------------------\n'

curl_json "${WORKER_URL}/health" > "$TMP/health.json"
python3 - <<'PY' "$TMP/health.json"
import json, sys
payload=json.load(open(sys.argv[1]))
assert payload["status"] == "ok"
assert payload["runtime"] == "firecracker"
assert payload["kvm"] is True
PY
printf '%-31s PASS\n' 'Health'

mkdir -p "$TMP/repo"
printf 'print("loom-firecracker-ok")\n' > "$TMP/repo/app.py"
mkdir -p "$TMP/repo/tests"
printf 'def test_ok():\n    assert 2 + 2 == 4\n' > "$TMP/repo/tests/test_basic.py"
# The host canary is written above. The VM must not be able to read it.

# The test repository must exist on the Firecracker worker's configured REPO_ROOT.
# Copying into that root is intentionally an explicit operator action rather than a client-controlled host path.
if [[ "${LOOM_FIRECRACKER_PREPARE_TEST_REPO:-false}" == "true" ]]; then
  mkdir -p "$REPO_PATH"
  rm -rf "${REPO_PATH:?}"/*
  cp -a "$TMP/repo/." "$REPO_PATH/"
fi

PAYLOAD="$(REPO_PATH="$REPO_PATH" python3 - <<'PY'
import json, os
print(json.dumps({
  "run_id": "e2e-basic",
  "org_id": "validation",
  "repo_path": os.environ["REPO_PATH"],
  "argv": ["python3", "-c", "print('loom-firecracker-ok')"],
  "timeout": 30,
  "network": False,
}))
PY
)"
JSON=$(REPO_PATH="$REPO_PATH" curl_json -X POST "${WORKER_URL}/execute" -d "$PAYLOAD")
python3 - <<'PY' "$JSON"
import json, sys
payload=json.loads(sys.argv[1])
assert payload["exit_code"] == 0
assert payload["stdout"].strip() == "loom-firecracker-ok"
assert payload["stderr"] == ""
PY
printf '%-31s PASS\n' 'Basic execution'

PAYLOAD='{"run_id":"e2e-timeout","org_id":"validation","repo_path":"'"$REPO_PATH"'","argv":["python3","-c","import time; time.sleep(300)"],"timeout":5,"network":false}'
JSON=$(curl_json -X POST "${WORKER_URL}/execute" -d "$PAYLOAD")
python3 - <<'PY' "$JSON"
import json,sys
p=json.loads(sys.argv[1]); assert p["exit_code"] == 124 and p["timed_out"] is True
PY
printf '%-31s PASS\n' 'Timeout enforcement'

PAYLOAD='{"run_id":"e2e-network","org_id":"validation","repo_path":"'"$REPO_PATH"'","argv":["python3","-c","import socket; socket.create_connection((\"1.1.1.1\",443),2)"],"timeout":5,"network":false}'
JSON=$(curl_json -X POST "${WORKER_URL}/execute" -d "$PAYLOAD")
python3 - <<'PY' "$JSON"
import json,sys
p=json.loads(sys.argv[1]); assert p["exit_code"] != 0
PY
printf '%-31s PASS\n' 'Network denial'

PAYLOAD='{"run_id":"e2e-secret","org_id":"validation","repo_path":"'"$REPO_PATH"'","argv":["python3","-c","from pathlib import Path; print(Path(\"/tmp/loom-secret-test\").read_text())"],"timeout":5,"network":false}'
JSON=$(curl_json -X POST "${WORKER_URL}/execute" -d "$PAYLOAD")
if grep -q "$CANARY" <<<"$JSON"; then
  echo 'Secret isolation         FAIL: host canary leaked' >&2
  exit 1
fi
printf '%-31s PASS\n' 'Secret isolation'

curl_json -X POST "${WORKER_URL}/recover" -d '{}' > "$TMP/recover.json"
printf '%-31s PASS\n' 'Recovery reconciliation'

printf '\nVALIDATION COMPLETE\n'
