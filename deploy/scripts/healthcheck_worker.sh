#!/bin/sh
set -eu

target="${WORKER_HEALTHCHECK_TARGET:-}"

case "$target" in
  ai-worker)
    lock_file="${AI_WORKER_LOCK_FILE:-/tmp/gentstationai_ai_worker.lock}"
    ;;
  telegram-worker)
    lock_file="${BOT_WORKER_LOCK_FILE:-/tmp/gentstationai_bot_worker.lock}"
    ;;
  report-scheduler)
    lock_file="${REPORT_SCHEDULER_LOCK_FILE:-/tmp/gentstationai_report_scheduler.lock}"
    ;;
  *)
    echo "Unsupported WORKER_HEALTHCHECK_TARGET: $target" >&2
    exit 1
    ;;
esac

[ -s "$lock_file" ]
pid="$(cat "$lock_file")"
kill -0 "$pid"
