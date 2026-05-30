#!/bin/sh
# Runs inside the backup container (cron @ 3am daily)
# Dumps seedance DB, keeps last BACKUP_KEEP_DAYS files.

KEEP="${BACKUP_KEEP_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="/backups/seedance_${TIMESTAMP}.sql.gz"

echo "$(date): Starting backup..."
pg_dump -h seedance-db -U seedance --no-owner --no-acl --clean seedance | gzip > "$FILE"

if [ -f "$FILE" ] && [ -s "$FILE" ]; then
    echo "$(date): Backup OK — $(du -h "$FILE" | cut -f1)"
    # Remove backups older than KEEP days
    find /backups -name "seedance_*.sql.gz" -mtime "+${KEEP}" -delete 2>/dev/null
    echo "$(date): Rotation done, $(ls /backups/*.sql.gz 2>/dev/null | wc -l) files kept"
else
    echo "$(date): Backup FAILED" >&2
    rm -f "$FILE"
fi
