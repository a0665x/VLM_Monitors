#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
export HF_HOME="${HF_HOME:-$PWD/temp/huggingface}"
PYTHON_BIN="${DECISION_PYTHON:-$PWD/.venv-decision/bin/python}"
if [[ ! -x "$PYTHON_BIN" && -x .venv-vllm/bin/python && -z "${DECISION_PYTHON:-}" ]]; then PYTHON_BIN="$PWD/.venv-vllm/bin/python"; fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Install the decision environment; see spec/STRUCTURED_DECISIONS.md" >&2
  exit 1
fi
exec "$PYTHON_BIN" -m uvicorn scripts.decision_server:app --host 127.0.0.1 --port 8001
