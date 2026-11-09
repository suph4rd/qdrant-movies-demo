#!/bin/sh
set -eu

exec text-embeddings-router \
    --model-id intfloat/multilingual-e5-small \
    --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3 \
    --dtype float32 \
    --port 18080
