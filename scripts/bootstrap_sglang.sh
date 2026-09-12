#!/usr/bin/env bash
# Official SGLang runtime; built-in continuous batching and RadixAttention caching.
set -euo pipefail
private_ip="$1"
env_file="$2"
set -a
source "$env_file"
set +a
sudo docker pull lmsysorg/sglang:v0.5.11-cu129-runtime
sudo docker build -t swarmci/sglang:gemma4 - <<'DOCKER'
FROM lmsysorg/sglang:v0.5.11-cu129-runtime
RUN python3 -m pip install --no-cache-dir distro jiter sniffio
RUN apt-get update -qq && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
DOCKER
sudo docker rm -f swarmci-gemma4 >/dev/null 2>&1 || true
# No --disable-radix-cache: prefix caching stays enabled. Model state is per replica.
exec sudo docker run --name swarmci-gemma4 --gpus all --ipc=host --shm-size 32g \
  -e NVIDIA_DISABLE_REQUIRE=true \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -p "$private_ip:8000:8000" \
  swarmci/sglang:gemma4 \
  python3 -m sglang.launch_server \
  --model-path google/gemma-4-E4B-it \
  --reasoning-parser gemma4 --tool-call-parser gemma4 \
  --attention-backend triton --mem-fraction-static 0.85 \
  --context-length 16384 --max-running-requests 64 \
  --chunked-prefill-size 4096 --schedule-policy lpm \
  --enable-metrics --host 0.0.0.0 --port 8000 --api-key "$MODEL_API_KEY"
