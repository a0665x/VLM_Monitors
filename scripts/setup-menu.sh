#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
printf '\nVLM Monitor · 安裝與服務管理\n偵測架構：%s\n\n' "$(uname -m)"
printf 'a) 一鍵準備主機與手機連線（首次使用）\n1) 安裝 / 更新 x86_64（Intel / AMD）\n2) 安裝 / 更新 aarch64（一般 ARM64 / Jetson）\n3) 啟動監控服務\n4) 重新啟動服務\n5) 查看服務狀態\n6) 安裝 vLLM（本專案 x86 CUDA 12.6 設定）\n7) 啟動 vLLM\n8) 停止 vLLM\n9) 啟用 Tailscale 私人分享\nd) 啟動平行分類服務（Qwen 1.5B）\ns) 停止平行分類服務／釋放 GPU\n0) 離開\n'
default_choice=a
[[ -x .venv/bin/python && -x temp/mediamtx ]] && default_choice=3
read -r -p "請選擇 [$default_choice]：" choice
case "${choice:-$default_choice}" in
  a|A) exec bash scripts/first-run.sh;;
  1|2)
    arch=x86_64; [[ "$choice" == 2 ]] && arch=aarch64
    bash scripts/bootstrap-local.sh --arch "$arch"
    read -r -p '安裝完成，現在啟動監控服務？[Y/n] ' start
    [[ "${start:-Y}" =~ ^[Yy]$ ]] && exec bash scripts/local-service.sh local-up
    ;;
  3) exec bash scripts/local-service.sh local-up;;
  4) exec bash scripts/local-service.sh local-restart;;
  5) exec bash scripts/local-service.sh local-status;;
  6) exec bash scripts/bootstrap-local.sh --vllm;;
  7) exec bash scripts/local-service.sh vllm-up;;
  8) exec bash scripts/local-service.sh vllm-down;;
  9)
    read -r -p '將持續開放相機與監控狀態給 Tailnet 中有權限的裝置。啟用？[y/N] ' share
    [[ "${share:-N}" =~ ^[Yy]$ ]] && exec bash scripts/local-service.sh local-tailnet
    ;;
  d|D) exec bash scripts/local-service.sh decision-up;;
  s|S) exec bash scripts/local-service.sh decision-down;;
  0) exit 0;;
  *) printf '無效選項\n' >&2; exit 2;;
esac
exit 0
