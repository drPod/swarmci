#!/usr/bin/env bash
set -euo pipefail
set -a
source "$HOME/swarmci-model.env"
set +a
export LD_LIBRARY_PATH="/usr/local/cuda-12.9/compat:${LD_LIBRARY_PATH:-}"
exec "$HOME/swarmci-model/.venv/bin/vllm" serve browser-use/bu-30b-a3b-preview \
 --host 127.0.0.1 --port 8000 --max-model-len 16384 --max-num-seqs 3 \
 --gpu-memory-utilization 0.9 --api-key "$MODEL_API_KEY"
