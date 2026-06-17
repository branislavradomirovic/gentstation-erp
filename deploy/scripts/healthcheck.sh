#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.prod.yml"
DISK_WARN_PCT="${DISK_WARN_PCT:-90}"
QUEUE_WARN_PENDING_SUBMISSIONS="${QUEUE_WARN_PENDING_SUBMISSIONS:-500}"
QUEUE_WARN_PENDING_CCTV="${QUEUE_WARN_PENDING_CCTV:-250}"
WORKER_STALE_SECONDS="${WORKER_STALE_SECONDS:-180}"

check_service() {
  service="$1"
  container_id="$(docker compose -f "$COMPOSE_FILE" ps -q "$service")"

  if [ -z "$container_id" ]; then
    echo "missing container: $service" >&2
    return 1
  fi

  state="$(docker inspect -f '{{.State.Status}}' "$container_id")"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"

  case "$health" in
    healthy|none) ;;
    *)
      echo "unhealthy container: $service ($state / $health)" >&2
      return 1
      ;;
  esac

  case "$state" in
    running) ;;
    *)
      echo "non-running container: $service ($state)" >&2
      return 1
      ;;
  esac
}

check_disk() {
  disk_pct="$(df -Pk "$REPO_ROOT" | awk 'NR==2 {gsub("%","",$5); print $5}')"
  if [ "${disk_pct:-0}" -ge "$DISK_WARN_PCT" ]; then
    echo "disk usage too high: ${disk_pct}% (threshold ${DISK_WARN_PCT}%)" >&2
    return 1
  fi
}

query_postgres_scalar() {
  sql="$1"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -lc \
    "psql -U \"\${POSTGRES_USER:-postgres}\" -d \"\${POSTGRES_DB:-gentstation}\" -t -A -c \"$sql\""
}

check_queue_health() {
  pending_submissions="$(query_postgres_scalar "SELECT COUNT(*) FROM submissions WHERE status = 'pending';" | tr -d '[:space:]')"
  pending_cctv="$(query_postgres_scalar "SELECT COUNT(*) FROM cctv_analysis_jobs WHERE status = 'pending';" | tr -d '[:space:]')"

  if [ "${pending_submissions:-0}" -ge "$QUEUE_WARN_PENDING_SUBMISSIONS" ]; then
    echo "pending submissions backlog too high: ${pending_submissions}" >&2
    return 1
  fi
  if [ "${pending_cctv:-0}" -ge "$QUEUE_WARN_PENDING_CCTV" ]; then
    echo "pending cctv backlog too high: ${pending_cctv}" >&2
    return 1
  fi
}

check_worker_heartbeats() {
  stale_count="$(query_postgres_scalar "WITH worker_keys AS (SELECT unnest(ARRAY['ai_processing_status','telegram_bot_status','report_scheduler_status','cctv_worker_status']) AS key) SELECT COUNT(*) FROM worker_keys wk LEFT JOIN system_settings ss ON ss.key = wk.key WHERE ss.value IS NULL OR COALESCE(((ss.value::jsonb)->>'last_update_ts')::numeric, 0) < EXTRACT(EPOCH FROM NOW()) - ${WORKER_STALE_SECONDS};" | tr -d '[:space:]')"
  if [ "${stale_count:-0}" -gt 0 ]; then
    echo "stale worker heartbeats detected: ${stale_count}" >&2
    return 1
  fi
}

for service in postgres redis web ai-worker telegram-worker report-scheduler reverse-proxy; do
  check_service "$service"
done

check_disk
check_queue_health
check_worker_heartbeats

echo "All GentStationAI production services and health thresholds are passing."
