#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${LOOM_FIRECRACKER_RUNTIME_DIR:-/var/lib/loom/firecracker}"
EVIDENCE_DIR="${LOOM_FIRECRACKER_EVIDENCE_DIR:-/var/lib/loom/evidence}"
BIN="${FIRECRACKER_BIN:-/usr/local/bin/firecracker}"
KERNEL="${LOOM_FIRECRACKER_KERNEL:-${RUNTIME_DIR}/kernel/vmlinux}"
ROOTFS="${LOOM_FIRECRACKER_ROOTFS:-${RUNTIME_DIR}/rootfs.ext4}"
WORKER_USER="${LOOM_FIRECRACKER_USER:-loom-sandbox}"
APPROVED_VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/infra/firecracker/VERSION")"
APPROVED_HASH_FILE="${ROOT_DIR}/infra/firecracker/SHA256SUM"

pass() { printf '%-23s PASS\n' "$1"; }
fail() { printf '%-23s FAIL: %s\n' "$1" "$2" >&2; exit 1; }

printf 'FIRECRACKER HOST VALIDATION\n---------------------------\n'

[[ "$(uname -s)" == "Linux" ]] || fail "Linux" "host is not Linux"
pass "Linux"
[[ "$(uname -m)" == "x86_64" ]] || fail "x86_64" "unsupported architecture $(uname -m)"
pass "x86_64"
[[ -e /dev/kvm && -r /dev/kvm && -w /dev/kvm ]] || fail "/dev/kvm" "KVM is missing or inaccessible"
pass "/dev/kvm"
command -v firecracker >/dev/null 2>&1 || true
[[ -x "$BIN" ]] || fail "Firecracker" "binary missing: $BIN"
pass "Firecracker"

VERSION_OUTPUT="$($BIN --version 2>&1 | head -n1)"
grep -Eq "${APPROVED_VERSION}" <<<"$VERSION_OUTPUT" || fail "Version" "expected ${APPROVED_VERSION}, got ${VERSION_OUTPUT}"
pass "Version"

EXPECTED_HASH="$(grep -E '^[0-9a-fA-F]{64}$' "$APPROVED_HASH_FILE" || true)"
[[ -n "$EXPECTED_HASH" ]] || fail "Binary hash" "infra/firecracker/SHA256SUM is still a placeholder"
ACTUAL_HASH="$(sha256sum "$BIN" | awk '{print $1}')"
[[ "$ACTUAL_HASH" == "$EXPECTED_HASH" ]] || fail "Binary hash" "hash mismatch"
pass "Binary hash"

[[ -f "$KERNEL" ]] || fail "Kernel" "missing $KERNEL"
pass "Kernel"
[[ -f "$ROOTFS" ]] || fail "Rootfs" "missing $ROOTFS"
pass "Rootfs"

id "$WORKER_USER" >/dev/null 2>&1 || fail "Worker identity" "user $WORKER_USER does not exist"
pass "Worker identity"
sudo -u "$WORKER_USER" test -r /dev/kvm || fail "Permissions" "$WORKER_USER cannot read /dev/kvm"
sudo -u "$WORKER_USER" test -w /dev/kvm || fail "Permissions" "$WORKER_USER cannot write /dev/kvm"
pass "Permissions"

mkdir -p "$RUNTIME_DIR" "$EVIDENCE_DIR"
[[ -w "$RUNTIME_DIR" ]] || fail "Runtime directory" "not writable: $RUNTIME_DIR"
[[ -w "$EVIDENCE_DIR" ]] || fail "Evidence directory" "not writable: $EVIDENCE_DIR"
pass "Runtime directory"
pass "Evidence directory"

DF_KB="$(df -Pk "$RUNTIME_DIR" | awk 'NR==2 {print $4}')"
(( DF_KB >= 30 * 1024 * 1024 )) || fail "Disk" "less than 30 GiB free"
pass "Disk"

MEM_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
(( MEM_KB >= 8 * 1024 * 1024 )) || fail "Memory" "less than 8 GiB RAM"
pass "Memory"

CPU_COUNT="$(nproc)"
(( CPU_COUNT >= 4 )) || fail "CPU" "less than 4 vCPU"
pass "CPU"

command -v tar >/dev/null 2>&1 || fail "tar" "tar is required for repository streaming"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum" "sha256sum is required"
command -v systemctl >/dev/null 2>&1 || fail "systemd" "systemctl is required"
pass "Prerequisites"

printf '\nREADY\n'
