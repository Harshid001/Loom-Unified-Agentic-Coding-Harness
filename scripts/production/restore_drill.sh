#!/usr/bin/env bash
# PRD-022 — Backup and Disaster Recovery Restore Drill Script
# Usage: ./scripts/production/restore_drill.sh <backup_file.tar.gz> <target_db_path>

set -euo pipefail

BACKUP_FILE="${1:-}"
TARGET_PATH="${2:-./restore_test.db}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file> [target_path]"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file '$BACKUP_FILE' does not exist."
    exit 1
fi

echo "[dr-drill] Starting disaster recovery restore drill..."
echo "[dr-drill] Source backup : $BACKUP_FILE"
echo "[dr-drill] Target path   : $TARGET_PATH"

python -c "
from loom.runtime.backup import verify_backup_integrity
ok = verify_backup_integrity('$BACKUP_FILE')
print('[dr-drill] Integrity verification:', 'PASSED' if ok else 'FAILED')
if not ok:
    exit(1)
"

echo "[dr-drill] Extracting backup payload..."
mkdir -p ./tmp_restore_drill
tar -xzf "$BACKUP_FILE" -C ./tmp_restore_drill

if [ -f "./tmp_restore_drill/records.db" ]; then
    cp ./tmp_restore_drill/records.db "$TARGET_PATH"
    echo "[dr-drill] Database restored to $TARGET_PATH"
fi

rm -rf ./tmp_restore_drill

echo "[dr-drill] DR Restore Drill completed successfully."
