#!/usr/bin/env bash
# PRD-022 — Backup and Disaster Recovery Restore Drill Script
# Usage: ./scripts/production/restore_drill.sh <backup_file.tar.gz> <target_path>

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
from pathlib import Path
from scripts.backup_restore import compute_sha256, _safe_extract
import tarfile, tempfile, shutil
backup = Path('$BACKUP_FILE').resolve()
target = Path('$TARGET_PATH').resolve()
tmp = Path(tempfile.mkdtemp(prefix='loom-restore-drill-'))
try:
    print('[dr-drill] Backup SHA256:', compute_sha256(backup))
    with tarfile.open(backup, 'r:gz') as tar:
        _safe_extract(tar, tmp)
    roots = [p for p in tmp.iterdir() if p.is_dir()]
    if not roots:
        raise SystemExit('No backup root directory found')
    db = next((p / 'records.db' for p in roots if (p / 'records.db').exists()), None)
    if db is None:
        raise SystemExit('records.db not found in backup')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, target)
    print('[dr-drill] Database restored to', target)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
"

echo "[dr-drill] DR Restore Drill completed successfully."
