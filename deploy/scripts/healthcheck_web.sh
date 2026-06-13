#!/bin/sh
set -eu

curl -fsS "http://127.0.0.1:${STREAMLIT_SERVER_PORT:-8501}/_stcore/health" >/dev/null
