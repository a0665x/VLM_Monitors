#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
arch="$(uname -m)"; dry_run=false; with_vllm=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) [[ $# -ge 2 ]] || { echo '--arch requires a value' >&2; exit 2; }; arch="$2"; shift;;
    --dry-run) dry_run=true;;
    --vllm) with_vllm=true;;
    *) echo "Unknown option: $1" >&2; exit 2;;
  esac
  shift
done
case "$arch" in
  x86|x86_64|amd64) arch=x86_64; asset=amd64;;
  aarch64|arm64) arch=aarch64; asset=arm64v8;;
  *) echo "Unsupported architecture: $arch" >&2; exit 2;;
esac
printf 'Architecture: %s\nMediaMTX: linux_%s\nOllama: official Linux installer (architecture auto-detected)\nCamera: portable software encoder, automatic device mode detection\n' "$arch" "$asset"
if $with_vllm && [[ "$arch" != x86_64 ]]; then
  echo 'This pinned CUDA 12.6 vLLM profile supports x86_64 only. ARM requires a hardware/JetPack-specific vLLM installation; configure VLLM_BASE_URL for an existing server.' >&2
  exit 2
fi
$dry_run && exit 0
[[ "$(uname -s)" == Linux && "$(uname -m)" == "$arch" ]] || { echo 'Selected architecture does not match this Linux host.' >&2; exit 2; }
mkdir -p temp logs
# Debian/Ubuntu install path; other distros can preinstall these prerequisites.
if ! command -v gst-launch-1.0 >/dev/null || ! command -v v4l2-ctl >/dev/null || ! command -v ffmpeg >/dev/null || ! command -v curl >/dev/null || ! /usr/bin/python3 -m pip --version >/dev/null 2>&1; then
  command -v apt-get >/dev/null || { echo 'Install Python 3.10+, pip, curl, GStreamer tools/plugins and v4l-utils, then rerun.' >&2; exit 1; }
  sudo apt-get update
  sudo apt-get install -y python3-pip python3-venv curl zstd ffmpeg v4l-utils gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
fi
if [[ ! -x temp/bootstrap/bin/uv ]]; then
  /usr/bin/python3 -m pip install --target temp/bootstrap uv==0.12.19
fi
uv_bin="$PWD/temp/bootstrap/bin/uv"
if [[ ! -x .venv/bin/python ]]; then "$uv_bin" venv --python /usr/bin/python3 .venv; fi
"$uv_bin" pip install --python .venv/bin/python -r requirements-service.txt
if [[ ! -x temp/mediamtx ]]; then
  curl -fsSL --retry 2 "https://github.com/bluenviron/mediamtx/releases/download/v1.21.1/mediamtx_v1.21.1_linux_${asset}.tar.gz" -o temp/mediamtx.tar.gz
  tar -xzf temp/mediamtx.tar.gz -C temp mediamtx
  chmod +x temp/mediamtx
fi
[[ -f .env ]] || cp config/local.env.example .env
[[ -f .env.vllm ]] || cp config/vllm.env.example .env.vllm
if ! command -v ollama >/dev/null; then
  curl -fsSL --retry 2 https://ollama.com/install.sh -o temp/install-ollama.sh
  sh temp/install-ollama.sh
fi
if ! curl -fsS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null; then
  sudo systemctl enable --now ollama
fi
ollama pull "${INSTALL_OLLAMA_MODEL:-qwen2.5vl:3b}"
if $with_vllm; then
  command -v nvidia-smi >/dev/null || { echo 'This vLLM profile requires NVIDIA CUDA; install the driver first.' >&2; exit 1; }
  if [[ ! -x .venv-vllm/bin/python ]]; then "$uv_bin" venv --python /usr/bin/python3 .venv-vllm; fi
  "$uv_bin" pip install --python .venv-vllm/bin/python -r requirements-vllm.txt --torch-backend=cu126
fi
if ! command -v tailscale >/dev/null; then
  curl -fsSL --retry 2 https://tailscale.com/install.sh -o temp/install-tailscale.sh
  sh temp/install-tailscale.sh
fi
echo 'Ready. Run ./run.sh local-up. Review .env if your camera needs a specific video mode.'
