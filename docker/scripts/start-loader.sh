#!/bin/sh
set -eu

python docker/scripts/wait_for_qdrant.py
exec python -m engine.load --url "$QDRANT_URL"
