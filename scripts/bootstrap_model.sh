#!/usr/bin/env bash
# On a Lambda model host: bash bootstrap_model.sh bu|gemma /absolute/path/model.env
set -euo pipefail
role="$1"
env_file="$2"
set -a
source "$env_file"
set +a
mkdir -p "$HOME/swarmci-model"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv venv "$HOME/swarmci-model/.venv" --python 3.12
uv pip install --python "$HOME/swarmci-model/.venv/bin/python" 'vllm==0.12.0'
if [[ "$role" == bu ]]; then
  model=browser-use/bu-30b-a3b-preview
  served=browser-use/bu-30b-a3b-preview
  length=16384
  seqs=3
else
  model=unsloth/gemma-3-4b-it
  served=google/gemma-3-4b-it
  length=8192
  seqs=64
  if [[ "$role" == gemma ]]; then seqs=16; fi
fi
# Listen on loopback: inference is reached through the SSH tunnel only.
exec "$HOME/swarmci-model/.venv/bin/vllm" serve "$model" \
  --served-model-name "$served" --host 127.0.0.1 --port 8000 \
  --max-model-len "$length" --max-num-seqs "$seqs" \
  --gpu-memory-utilization 0.9 --api-key "$MODEL_API_KEY"
