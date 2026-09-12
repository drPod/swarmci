#!/usr/bin/env bash
set -euo pipefail
set -a
source "$HOME/swarmci-model.env"
set +a
exec "$HOME/swarmci-router/bin/python" -m sglang_router.launch_router \
 --host 10.19.31.67 --port 30000 --policy cache_aware \
 --api-key "$MODEL_API_KEY" --prometheus-host 127.0.0.1 --prometheus-port 29000 \
 --worker-startup-timeout-secs 1200
