#!/bin/sh
set -eu

python backend/scripts/wait_for_qdrant.py
exec python -m backend.engine.load --url "$QDRANT_URL"
