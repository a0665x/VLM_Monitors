#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env.vllm ]]; then set -a; source .env.vllm; set +a; fi
export HF_HOME="${HF_HOME:-$PWD/temp/huggingface}"
export VLLM_USE_V1="${VLLM_USE_V1:-0}"
export VLLM_ATTENTION_BACKEND="${VLLM_ATTENTION_BACKEND:-XFORMERS}"
export VLLM_NO_USAGE_STATS=1
exec .venv-vllm/bin/vllm serve "${VLLM_MODEL:-Qwen/Qwen2.5-VL-3B-Instruct}" \
  --host "${VLLM_HOST:-127.0.0.1}" --port "${VLLM_PORT:-8000}" \
  --dtype half --max-model-len "${VLLM_MAX_MODEL_LEN:-2048}" \
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.85}" \
  --max-num-seqs 1 --enforce-eager --swap-space 0 \
  --limit-mm-per-prompt '{"image":1,"video":0}' \
  --mm-processor-kwargs '{"min_pixels":200704,"max_pixels":200704}'
