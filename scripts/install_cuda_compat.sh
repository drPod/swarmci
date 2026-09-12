#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f /usr/local/cuda-12.9/compat/libcuda.so.1 ]]; then
  curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/swarmci-cuda-keyring.deb
  sudo dpkg -i /tmp/swarmci-cuda-keyring.deb
  sudo apt-get update -qq
  sudo apt-get install -y cuda-compat-12-9
fi
