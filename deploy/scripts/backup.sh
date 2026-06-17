#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
DB_BASENAME="gentstation_${TIMESTAMP}"

mkdir -p "$BACKUP_DIR"

echo "Starting GentStationAI Postgres backup: $TIMESTAMP"

docker compose -f "$COMPOSE_FILE" exec -T postgres sh -lc \
  'pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-gentstation}" -Fc' \
  > "$BACKUP_DIR/${DB_BASENAME}.dump"

cat > "$BACKUP_DIR/${DB_BASENAME}.manifest.json" <<EOF
{"timestamp":"$TIMESTAMP","format":"pg_dump_custom","storage":"postgres_only","notes":"Submission media, CCTV evidence, and import blobs are stored in Postgres."}
EOF

find "$BACKUP_DIR" -type f -mtime +"$RETENTION_DAYS" -delete

echo "Backup complete: $BACKUP_DIR/${DB_BASENAME}.dump"
