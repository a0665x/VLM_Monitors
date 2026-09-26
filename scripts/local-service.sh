#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
install_unit() {
  local unit="$1" launcher="$2"
  .venv/bin/python - "$unit" "$launcher" <<'UNITPY'
import os,sys
from pathlib import Path
unit,launcher=sys.argv[1:]
root=Path.cwd()
target=Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")))/"systemd/user"/(unit+".service")
target.parent.mkdir(parents=True,exist_ok=True)
def quote(value): return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
target.write_text("[Unit]\nDescription=VLM Monitors "+unit+"\nAfter=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory="+str(root).replace("%", "%%")+"\nExecStart=/bin/bash "+quote(root/launcher)+"\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=20\nKillMode=control-group\nEnvironment=PYTHONUNBUFFERED=1\n\n[Install]\nWantedBy=default.target\n")
print(target)
UNITPY
  systemctl --user daemon-reload
}
wait_local() {
  for ((attempt=0; attempt<30; attempt++)); do
    if curl -fsS --max-time 1 http://127.0.0.1:5000/auth/status >/dev/null 2>&1; then
      echo "主機已就緒：http://127.0.0.1:5000/"
      echo "首頁上方可直接掃 QR code，手機可查看所有相機或分享自己的相機。"
      return 0
    fi
    sleep 1
  done
  echo "Service did not become ready; run ./run.sh local-logs" >&2
  return 1
}
case "${1:-local-status}" in
  local-up)
    install_unit vlm-monitor scripts/start-local.sh
    systemctl --user enable --now vlm-monitor.service
    wait_local
    ;;
  local-restart) systemctl --user restart vlm-monitor.service; wait_local ;;
  local-down) systemctl --user disable --now vlm-monitor.service ;;
  local-status) systemctl --user status vlm-monitor.service --no-pager ;;
  local-logs) journalctl --user -u vlm-monitor.service -n 80 --no-pager ;;
  local-tailnet)
    tailscale serve --bg --https=443 http://127.0.0.1:5000
    if systemctl --user is-active --quiet vlm-monitor.service; then
      systemctl --user restart vlm-monitor.service
      wait_local
    fi
    ;;
  decision-up)
    install_unit vlm-decision scripts/start-decision.sh
    systemctl --user enable --now vlm-decision.service
    ;;
  decision-down) systemctl --user disable --now vlm-decision.service ;;
  decision-status) systemctl --user status vlm-decision.service --no-pager ;;
  decision-logs) journalctl --user -u vlm-decision.service -n 60 --no-pager ;;
  vllm-up)
    install_unit vlm-vllm scripts/start-vllm.sh
    systemctl --user start vlm-vllm.service
    ;;
  vllm-down) systemctl --user stop vlm-vllm.service ;;
  vllm-status) systemctl --user status vlm-vllm.service --no-pager ;;
  vllm-logs) journalctl --user -u vlm-vllm.service -n 80 --no-pager ;;
  *) echo "Unsupported command: $1" >&2; exit 2 ;;
esac
