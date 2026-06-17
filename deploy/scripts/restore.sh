#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
TIMESTAMP="${1:-}"

if [ -z "$TIMESTAMP" ]; then
  echo "Usage: ./restore.sh YYYYMMDD_HHMMSS" >&2
  exit 1
fi

DUMP_FILE="$BACKUP_DIR/gentstation_${TIMESTAMP}.dump"
if [ ! -f "$DUMP_FILE" ]; then
  echo "Backup not found: $DUMP_FILE" >&2
  exit 1
fi

echo "WARNING: This will replace the target Postgres database with backup $TIMESTAMP."
printf "Type RESTORE to continue: "
read -r confirm
if [ "$confirm" != "RESTORE" ]; then
  echo "Restore aborted."
  exit 1
fi

cat "$DUMP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T postgres sh -lc \
  'pg_restore --clean --if-exists --no-owner --no-privileges -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-gentstation}"'

echo "Restore complete. Restarting services..."
docker compose -f "$COMPOSE_FILE" restart
