#!/usr/bin/env bash
# Inicia el backend FastAPI en http://127.0.0.1:${PORT:-8000} (documentación en /docs). Otro puerto: PORT=8001 ./scripts/run_backend.sh
set -euo pipefail
cd "$(dirname "$0")/../backend"
if [ ! -f .env ]; then echo "Falta backend/.env: copien .env.example y pongan una API_KEY"; exit 1; fi
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
exec .venv/bin/uvicorn app.main:app_factory --factory --host 127.0.0.1 --port "${PORT:-8000}"
