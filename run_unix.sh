#!/usr/bin/env sh
set -eu
if [ ! -f .env ]; then cp .env.example .env; fi
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
