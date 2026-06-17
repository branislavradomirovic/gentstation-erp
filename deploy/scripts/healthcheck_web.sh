#!/bin/sh
set -eu

host="${STREAMLIT_SERVER_ADDRESS:-127.0.0.1}"
port="${STREAMLIT_SERVER_PORT:-8501}"
if [ "$host" = "0.0.0.0" ] || [ "$host" = "::" ]; then
  host=127.0.0.1
fi
curl -fsS "http://${host}:${port}/_stcore/health" >/dev/null
