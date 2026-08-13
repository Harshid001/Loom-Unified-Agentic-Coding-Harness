#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_ROOT="${1:-/}"
install -D -m 0755 "${ROOT_DIR}/loom/sandbox/firecracker_guest_agent.py" "${TARGET_ROOT}/usr/local/bin/loom_guest_agent.py"
install -D -m 0644 "${ROOT_DIR}/infra/firecracker/guest-agent.service" "${TARGET_ROOT}/etc/systemd/system/loom-firecracker-guest-agent.service"
