#!/usr/bin/env bash
# Apply DB migrations (and optionally seed) before launching the given command.
set -euo pipefail

echo "[entrypoint] Running Alembic migrations…"
alembic upgrade head

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "[entrypoint] Seeding baseline data…"
  python -m scripts.seed || echo "[entrypoint] seed failed (continuing)"
fi

echo "[entrypoint] Starting: $*"
exec "$@"
