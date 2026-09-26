#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo '步驟 1/3：準備主機與推論環境'
if [[ ! -x .venv/bin/python || ! -x temp/mediamtx ]] || ! command -v ollama >/dev/null || ! command -v tailscale >/dev/null; then
  bash scripts/bootstrap-local.sh --arch "$(uname -m)"
fi
echo '步驟 2/3：啟動主機相機與監控頁面'
bash scripts/local-service.sh local-up
echo '步驟 3/3：手機連線設定'
if ! tailscale status --json | .venv/bin/python -c 'import json,sys;sys.exit(json.load(sys.stdin).get("BackendState")!="Running")'; then
  echo '請依 Tailscale 顯示的網址登入，手機也需要加入同一個網路。'
  sudo tailscale up
fi
if ! curl -fsS http://127.0.0.1:5000/api/share | .venv/bin/python -c 'import json,sys;sys.exit(not json.load(sys.stdin).get("ready"))'; then
  read -r -p '啟用手機掃碼連線？同一 Tailnet 中有存取權的裝置將可觀看與分享影像。[Y/n] ' enable
  if [[ "${enable:-Y}" =~ ^[Yy]$ ]]; then
    tailscale serve --bg --https=443 http://127.0.0.1:5000 || sudo tailscale serve --bg --https=443 http://127.0.0.1:5000
    bash scripts/local-service.sh local-restart
  fi
fi
echo '完成。請開啟 http://127.0.0.1:5000/，首頁直接顯示手機 QR code。'
echo '手機：開啟 Tailscale → 掃碼 → 查看所有相機 / 分享我的相機。'
