#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

# `import venv` succeeds even when the stdlib ensurepip data is missing, which
# is what actually makes `python3 -m venv` fail on Debian/Ubuntu. Probe for
# ensurepip so the guard reflects real venv-creation capability.
if ! python3 -c "import ensurepip" 2>/dev/null; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv
fi

test -f .env || cp .env.example .env

# Backend API service (FastAPI).
python3 -m venv backend/.venv
backend/.venv/bin/pip install -q --upgrade pip
backend/.venv/bin/pip install -q -r backend/requirements.txt
if [ -f backend/requirements-dev.txt ]; then
  backend/.venv/bin/pip install -q -r backend/requirements-dev.txt
fi

# Create/upgrade the database schema. The dev terminals launch uvicorn directly
# (unlike the Dockerfile, which runs migrations first), so apply migrations here.
# `alembic upgrade head` is idempotent and, for the default SQLite database, the
# resulting file is durable state that later boots can reuse.
(cd backend && .venv/bin/alembic upgrade head)

# ML signal service (FastAPI + scikit-learn).
python3 -m venv ml-service/.venv
ml-service/.venv/bin/pip install -q --upgrade pip
ml-service/.venv/bin/pip install -q -r ml-service/requirements.txt

# Frontend (Next.js).
npm ci --prefix frontend --prefer-offline
