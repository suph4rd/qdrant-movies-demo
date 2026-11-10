#!/bin/sh
set -eu

exec python -m uvicorn backend.api.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --port 18000
