#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${SUPABASE_URL:?Set SUPABASE_URL}"
: "${SUPABASE_SERVICE_ROLE_KEY:?Set SUPABASE_SERVICE_ROLE_KEY}"

mkdir -p logs

exec .venv/bin/python -m src.supabase_exporter \
  --db "${DEEP_THOUGHT_DB_PATH:-logs/deep_thought.db}" \
  --state "${SUPABASE_EXPORT_STATE:-logs/supabase_exporter_state.json}" \
  --interval "${SUPABASE_EXPORT_INTERVAL:-5}"
