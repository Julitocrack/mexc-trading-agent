#!/usr/bin/env bash
# Inicia la UI (Vue + Vite) en http://127.0.0.1:5173 con proxy /api → backend.
set -euo pipefail
cd "$(dirname "$0")/../frontend"
[ -d node_modules ] || npm install
exec npm run dev
