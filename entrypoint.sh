#!/bin/sh
set -eu
mkdir -p /data /data/backups
chown -R appuser:appuser /data
if [ "${LEADORA_WORKER_ENABLED:-1}" = "1" ]; then
  # Worker has an independent retry loop and shares the persistent SQLite volume.
  gosu appuser python -m app.worker &
fi
exec gosu appuser uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
