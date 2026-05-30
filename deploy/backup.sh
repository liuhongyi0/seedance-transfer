#!/bin/bash
# Seedance Studio — PostgreSQL backup
# Supports: manual dump, automated rotation (daily/weekly/monthly), S3 upload
#
# Usage:
#   ./deploy/backup.sh                          # manual dump to ./backups/
#   ./deploy/backup.sh --s3 s3://my-bucket/     # dump + upload to S3
#   ./deploy/backup.sh --restore backups/seedance_20260101.sql  # restore from file
#
# Cron (daily at 3am):
#   0 3 * * * /opt/seedance/deploy/backup.sh --rotate >> /var/log/seedance-backup.log 2>&1

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[backup]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
die()  { echo -e "${RED}[error]${NC} $1"; exit 1; }

DEPLOY_DIR="${DEPLOY_DIR:-/opt/seedance}"
BACKUP_DIR="${BACKUP_DIR:-${DEPLOY_DIR}/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/seedance_${TIMESTAMP}.sql.gz"

# ── Parse args ───────────────────────────────────────────────────────────
MODE="dump"
S3_PATH=""
RESTORE_FILE=""
DO_ROTATE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --s3)      MODE="s3"; S3_PATH="$2"; shift 2 ;;
        --restore) MODE="restore"; RESTORE_FILE="$2"; shift 2 ;;
        --rotate)  DO_ROTATE=1; shift ;;
        *)         die "Unknown arg: $1" ;;
    esac
done

mkdir -p "$BACKUP_DIR"

# ── Dump ─────────────────────────────────────────────────────────────────
do_dump() {
    log "Dumping PostgreSQL database..."
    docker compose -f "${DEPLOY_DIR}/docker-compose.yml" exec -T db \
        pg_dump -U seedance --no-owner --no-acl --clean \
        seedance | gzip > "$BACKUP_FILE"
    log "Backup saved: ${BACKUP_FILE} ($(du -h "$BACKUP_FILE" | cut -f1))"
}

# ── Restore ──────────────────────────────────────────────────────────────
do_restore() {
    local f="$1"
    if [ ! -f "$f" ]; then
        die "Backup file not found: $f"
    fi
    log "Restoring from: $f"
    if [[ "$f" == *.gz ]]; then
        gunzip -c "$f" | docker compose -f "${DEPLOY_DIR}/docker-compose.yml" exec -T db \
            psql -U seedance -d seedance
    else
        docker compose -f "${DEPLOY_DIR}/docker-compose.yml" exec -T db \
            psql -U seedance -d seedance < "$f"
    fi
    log "Restore complete."
}

# ── S3 upload ────────────────────────────────────────────────────────────
do_s3() {
    do_dump
    log "Uploading to S3: ${S3_PATH}"
    aws s3 cp "$BACKUP_FILE" "${S3_PATH}/$(basename "$BACKUP_FILE")" \
        --storage-class STANDARD_IA 2>/dev/null || \
        die "S3 upload failed. Install awscli and configure credentials."
    log "S3 upload complete."
}

# ── Rotation ─────────────────────────────────────────────────────────────
do_rotation() {
    log "Rotating old backups..."

    # Daily: keep last 7
    find "$BACKUP_DIR" -name "seedance_*.sql.gz" -mtime +7 -delete 2>/dev/null || true

    # Weekly (Sundays): keep last 4
    local sunday_files=$(find "$BACKUP_DIR" -name "seedance_*Sun*.sql.gz" 2>/dev/null || true)
    if [ -n "$sunday_files" ]; then
        echo "$sunday_files" | sort -r | tail -n +5 | xargs rm -f 2>/dev/null || true
    fi

    # Keep a "latest" symlink
    ln -sf "$(basename "$BACKUP_FILE")" "${BACKUP_DIR}/seedance_latest.sql.gz"
    log "Rotation done. Backups: $(ls "$BACKUP_DIR"/*.sql.gz 2>/dev/null | wc -l) files"
}

# ── Main ─────────────────────────────────────────────────────────────────
case "$MODE" in
    dump)
        do_dump
        [ "$DO_ROTATE" = "1" ] && do_rotation
        ;;
    s3)
        do_s3
        [ "$DO_ROTATE" = "1" ] && do_rotation
        ;;
    restore)
        do_restore "$RESTORE_FILE"
        ;;
esac

log "Done."
