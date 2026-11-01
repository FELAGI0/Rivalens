#!/bin/bash
# Daily PostgreSQL backup for Rivalens (7-day retention).
# Cron example: 0 3 * * * /opt/Rivalens/deploy/backup.sh >> /var/log/rivalens-backup.log 2>&1
set -euo pipefail

BACKUP_DIR=/opt/Rivalens/backups
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="$BACKUP_DIR/rivalens_${TIMESTAMP}.sql.gz"

docker compose -f /opt/Rivalens/docker-compose.prod.yml \
  --env-file /opt/Rivalens/.env.prod exec -T postgres \
  pg_dump -U rivalens rivalens | gzip > "$FILE"

# Keep the 7 most recent backups, delete the rest.
ls -t "$BACKUP_DIR"/rivalens_*.sql.gz | tail -n +8 | xargs -r rm

echo "Backup: $FILE"
