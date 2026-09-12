#!/usr/bin/env bash
set -euo pipefail
private_ip="$1"
head_ip="$2"
role="$3"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
mkdir -p "$HOME/swarmci"
tar -xzf "$HOME/swarmci-code.tar.gz" -C "$HOME/swarmci"
cd "$HOME/swarmci"
sed -i 's/name="swarmci-execution" content="local"/name="swarmci-execution" content="ray"/' swarmci/static/index.html
uv sync --frozen --python 3.12
uv run playwright install --with-deps chromium
set -a
source .env
set +a
if [[ "$role" == head ]]; then
  uv run ray start --head --node-ip-address "$private_ip" --port 6379 \
    --dashboard-host 127.0.0.1 --dashboard-port 8265 --num-cpus 28 --num-gpus 0 \
    --resources '{"browser":32}' --disable-usage-stats
  nohup uv run uvicorn swarmci.api:app --host "$private_ip" --port 8080 > "$HOME/swarmci-api.log" 2>&1 < /dev/null &
else
  uv run ray start --address "$head_ip:6379" --node-ip-address "$private_ip" \
    --num-cpus 28 --num-gpus 0 --resources '{"browser":32}' --disable-usage-stats
fi
