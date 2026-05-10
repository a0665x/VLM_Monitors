#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-help}"
shift || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SERVICE_NAME="llm-monitor"
CONTAINER_NAME="llm_monitor"
IMAGE_NAME="llm-monitor:latest"

WEB_URL="http://localhost:5000"
API_STATUS_URL="$WEB_URL/api/status"
API_VIDEO_DEVICES_URL="$WEB_URL/api/devices/video"
API_AUDIO_DEVICES_URL="$WEB_URL/api/devices/audio"
HLS_URL="http://localhost:8888/camera/index.m3u8"
WEBRTC_URL="http://localhost:8889/camera"
RTSP_HOST="127.0.0.1"
RTSP_PORT="8554"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
LAN_IP=""

FOLLOW_LOGS=false
START_NGROK=true
FORCE_BUILD=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --follow|-f)
      FOLLOW_LOGS=true
      ;;
    --no-ngrok)
      START_NGROK=false
      ;;
    --no-build)
      FORCE_BUILD=false
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

green() { printf '\033[32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[33m%s\033[0m\n' "$1"; }
red() { printf '\033[31m%s\033[0m\n' "$1"; }
blue() { printf '\033[34m%s\033[0m\n' "$1"; }

step() { blue "[STEP] $1"; }
ok() { green "[ OK ] $1"; }
warn() { yellow "[WARN] $1"; }
fail() { red "[FAIL] $1"; exit 1; }

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

detect_ngrok_user_config() {
  local candidate=""
  if [[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/ngrok/ngrok.yml" ]]; then
    candidate="${XDG_CONFIG_HOME:-$HOME/.config}/ngrok/ngrok.yml"
  elif [[ -f "$HOME/.ngrok2/ngrok.yml" ]]; then
    candidate="$HOME/.ngrok2/ngrok.yml"
  fi
  printf '%s' "$candidate"
}

detect_lan_ip() {
  local ip_candidate=""

  if command_exists ip; then
    ip_candidate="$(ip route get 1.1.1.1 2>/dev/null | awk '/src/ {for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' || true)"
  fi

  if [[ -z "$ip_candidate" ]] && command_exists hostname; then
    ip_candidate="$(hostname -I 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i !~ /^127\./) {print $i; exit}}' || true)"
  fi

  LAN_IP="$ip_candidate"
}

compose() {
  docker compose "$@"
}

container_id() {
  compose ps -q "$SERVICE_NAME" 2>/dev/null || true
}

container_state() {
  local id
  id="$(container_id)"
  if [[ -z "$id" ]]; then
    printf 'missing'
    return
  fi
  docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || printf 'unknown'
}

require_file() {
  local path="$1"
  [[ -e "$path" ]] || fail "Required path not found: $path"
}

check_prereqs() {
  step "Checking project prerequisites"
  require_file "Dockerfile"
  require_file "docker-compose.yml"
  require_file "mediamtx.yml"
  require_file "temp/mediamtx"

  [[ -x "temp/mediamtx" ]] || fail "temp/mediamtx exists but is not executable"
  command_exists docker || fail "docker not found"
  command_exists curl || fail "curl not found"
  docker compose version >/dev/null || fail "docker compose is not available"
  docker info >/dev/null || fail "Docker daemon is not reachable"

  mkdir -p data logs temp
  ok "Project prerequisites look good"
}

check_nvidia_runtime() {
  step "Checking NVIDIA Docker runtime"
  if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
    ok "NVIDIA runtime is available"
  else
    fail "NVIDIA runtime is missing. Install NVIDIA Container Toolkit and configure Docker runtime before starting this project."
  fi
}

check_host_devices() {
  step "Checking host camera and audio devices"
  [[ -e /dev/video0 ]] || fail "/dev/video0 not found; connect a camera or update docker-compose.yml VIDEO_DEVICE"
  if [[ -e /dev/snd ]]; then
    ok "Audio device tree exists at /dev/snd"
  else
    warn "/dev/snd not found; sound detection/audio capture may not work"
  fi
  ok "Video device exists at /dev/video0"
}

check_ollama() {
  step "Checking Ollama"
  if curl -fsS --max-time 3 "$OLLAMA_URL/api/tags" >/dev/null; then
    ok "Ollama is reachable at $OLLAMA_URL"
  else
    fail "Ollama is not reachable at $OLLAMA_URL. Start it first, for example: ollama serve"
  fi
}

wait_http() {
  local label="$1"
  local url="$2"
  local attempts="${3:-45}"
  local delay="${4:-2}"

  step "Waiting for $label"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 3 "$url" >/dev/null; then
      ok "$label is reachable: $url"
      return 0
    fi
    sleep "$delay"
  done
  warn "Recent container logs:"
  compose logs --tail 80 "$SERVICE_NAME" || true
  fail "$label did not become reachable: $url"
}

wait_tcp() {
  local label="$1"
  local host="$2"
  local port="$3"
  local attempts="${4:-30}"
  local delay="${5:-2}"

  step "Waiting for $label"
  for _ in $(seq 1 "$attempts"); do
    if (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1; then
      ok "$label is accepting TCP connections at $host:$port"
      return 0
    fi
    sleep "$delay"
  done
  warn "Recent container logs:"
  compose logs --tail 80 "$SERVICE_NAME" || true
  fail "$label did not open TCP port $host:$port"
}

check_container_running() {
  step "Checking container state"
  local state
  state="$(container_state)"
  if [[ "$state" == "running" ]]; then
    ok "Container $CONTAINER_NAME is running"
  else
    compose ps || true
    fail "Container $CONTAINER_NAME is not running (state=$state)"
  fi
}

check_container_devices() {
  step "Checking devices inside container"
  if compose exec -T "$SERVICE_NAME" test -e /dev/video0; then
    ok "Container can see /dev/video0"
  else
    fail "Container cannot see /dev/video0"
  fi

  if compose exec -T "$SERVICE_NAME" test -e /dev/snd; then
    ok "Container can see /dev/snd"
  else
    warn "Container cannot see /dev/snd; sound detection/audio capture may be unavailable"
  fi
}

check_device_apis() {
  wait_http "video device API" "$API_VIDEO_DEVICES_URL" 20 2
  wait_http "audio device API" "$API_AUDIO_DEVICES_URL" 20 2
}

start_ngrok_if_available() {
  if [[ "$START_NGROK" != true ]]; then
    return
  fi

  step "Checking optional ngrok"
  if ! command_exists ngrok; then
    warn "ngrok not found; skipping public URL"
    return
  fi

  pkill -x ngrok >/dev/null 2>&1 || true
  rm -f data/ngrok_url.txt data/ngrok_webrtc_url.txt
  mkdir -p data
  rm -f logs/ngrok-ui.log logs/ngrok-webrtc.log
  cat > data/ngrok.yml <<'EOF'
version: "2"
web_addr: 127.0.0.1:4040
tunnels:
  ui:
    proto: http
    addr: 5000
  webrtc:
    proto: http
    addr: 8889
EOF
  local ngrok_user_config=""
  local ngrok_config_arg="data/ngrok.yml"
  ngrok_user_config="$(detect_ngrok_user_config)"
  if [[ -n "$ngrok_user_config" ]]; then
    ngrok_config_arg="${ngrok_user_config},data/ngrok.yml"
  fi
  nohup ngrok start --all --config "$ngrok_config_arg" --log=stdout > logs/ngrok-ui.log 2>&1 &
  sleep 3

  local tunnels_json=""
  tunnels_json="$(curl -fsS --max-time 3 localhost:4040/api/tunnels 2>/dev/null || true)"

  local ngrok_url
  ngrok_url="$(printf '%s' "$tunnels_json" | python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
for tunnel in data.get("tunnels", []):
    if tunnel.get("name") == "ui":
        print(tunnel.get("public_url", ""))
        break
' 2>/dev/null || true)"
  if [[ -n "$ngrok_url" ]]; then
    printf '%s\n' "$ngrok_url" > data/ngrok_url.txt
    ok "Ngrok public URL: $ngrok_url"
  else
    warn "ngrok started but no public URL was returned"
    if [[ -s logs/ngrok-ui.log ]]; then
      warn "ngrok UI log:"
      tail -n 20 logs/ngrok-ui.log || true
    fi
  fi

  local ngrok_webrtc_url
  ngrok_webrtc_url="$(printf '%s' "$tunnels_json" | python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
for tunnel in data.get("tunnels", []):
    if tunnel.get("name") == "webrtc":
        print(tunnel.get("public_url", ""))
        break
' 2>/dev/null || true)"
  if [[ -n "$ngrok_webrtc_url" ]]; then
    printf '%s\n' "$ngrok_webrtc_url" > data/ngrok_webrtc_url.txt
    ok "Ngrok WebRTC URL: $ngrok_webrtc_url"
  else
    warn "ngrok WebRTC URL was not returned; phone Camera SRC may need local HTTPS setup"
    if [[ -s logs/ngrok-webrtc.log ]]; then
      warn "ngrok WebRTC log:"
      tail -n 20 logs/ngrok-webrtc.log || true
    elif [[ -s logs/ngrok-ui.log ]]; then
      warn "ngrok combined log:"
      tail -n 20 logs/ngrok-ui.log || true
    fi
  fi
}

print_urls() {
  detect_lan_ip
  printf '\n'
  ok "VLM_Monitors is ready"
  printf 'Web UI     : %s\n' "$WEB_URL"
  if [[ -n "$LAN_IP" ]]; then
    printf 'LAN UI     : http://%s:5000\n' "$LAN_IP"
    printf 'LAN WebRTC : http://%s:8889/camera\n' "$LAN_IP"
    printf 'LAN HLS    : http://%s:8888/camera/index.m3u8\n' "$LAN_IP"
    printf 'LAN note   : Desktop browsers on the same network can use this HTTP UI.\n'
  else
    warn "Could not detect a LAN IP automatically; use this host's same-network IP with port 5000."
  fi
  if [[ -s data/ngrok_url.txt ]]; then
    printf 'Public UI  : %s\n' "$(cat data/ngrok_url.txt)"
    printf 'Phone URL  : %s\n' "$(cat data/ngrok_url.txt)"
  fi
  if [[ -s data/ngrok_webrtc_url.txt ]]; then
    printf 'Public RTC : %s\n' "$(cat data/ngrok_webrtc_url.txt)"
    printf 'Phone note : Open the HTTPS Public UI on the phone, then switch to Camera SRC so Safari can request camera permission.\n'
  fi
  printf 'WebRTC view: %s\n' "$WEBRTC_URL"
  printf 'RTSP stream: rtsp://localhost:%s/camera\n' "$RTSP_PORT"
  printf 'HLS stream : %s\n' "$HLS_URL"
  printf 'Ollama     : %s\n' "$OLLAMA_URL"
  printf '\n'
  printf 'How to open:\n'
  printf '  1. Situation Room host on this AGX: %s\n' "$WEB_URL"
  if [[ -n "$LAN_IP" ]]; then
    printf '  2. Same-network desktop UI       : http://%s:5000\n' "$LAN_IP"
  fi
  if [[ -s data/ngrok_url.txt ]]; then
    printf '  3. Phone HTTPS UI                : %s\n' "$(cat data/ngrok_url.txt)"
  fi
  if [[ -s data/ngrok_webrtc_url.txt ]]; then
    printf '  4. Phone WebRTC base             : %s\n' "$(cat data/ngrok_webrtc_url.txt)"
  fi
  printf '\n'
  printf 'Phone Camera SRC steps:\n'
  if [[ -s data/ngrok_url.txt ]]; then
    printf '  - Open the HTTPS Public UI link above on the phone.\n'
  else
    printf '  - HTTPS is required for phone camera sharing. Start ngrok or another HTTPS tunnel first.\n'
  fi
  printf '  - Switch mode to Camera SRC.\n'
  printf '  - Enter source name / source id.\n'
  printf '  - Allow camera permission when the browser asks.\n'
  printf '  - Tap publish in the embedded WebRTC page.\n'
  printf '\n'
  printf 'Situation Room steps:\n'
  printf '  - Any client entering Situation Room controls the same backend dashboard.\n'
  printf '  - Wait for the iPhone source tile to appear.\n'
  printf '  - Click Monitor on the source you want to analyze.\n'
  printf '\n'
}

preflight() {
  check_prereqs
  check_nvidia_runtime
  check_host_devices
  check_ollama
}

bring_up() {
  preflight

  step "Starting Docker Compose stack"
  if [[ "$FORCE_BUILD" == true ]]; then
    compose up -d --build
  else
    compose up -d
  fi

  check_container_running
  check_container_devices
  wait_http "Flask API" "$API_STATUS_URL" 60 2
  wait_tcp "RTSP stream" "$RTSP_HOST" "$RTSP_PORT" 45 2
  wait_http "HLS stream" "$HLS_URL" 60 2
  check_device_apis
  start_ngrok_if_available
  print_urls

  if [[ "$FOLLOW_LOGS" == true ]]; then
    step "Tailing logs"
    compose logs -f "$SERVICE_NAME"
  fi
}

restart_stack() {
  preflight
  step "Stopping and removing existing Compose containers"
  compose down --remove-orphans
  ok "Existing Compose containers are down"
  bring_up
}

rebuild_stack() {
  preflight
  step "Stopping existing Compose containers"
  compose down --remove-orphans
  step "Rebuilding image without cache"
  compose build --no-cache
  FORCE_BUILD=false bring_up
}

status_stack() {
  check_prereqs
  printf '\n'
  step "Docker Compose status"
  compose ps || true

  printf '\n'
  step "Layer checks"
  if docker info >/dev/null 2>&1; then ok "Docker daemon is reachable"; else warn "Docker daemon is not reachable"; fi
  if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then ok "NVIDIA runtime is available"; else warn "NVIDIA runtime is missing"; fi
  if [[ -e /dev/video0 ]]; then ok "Host /dev/video0 exists"; else warn "Host /dev/video0 missing"; fi
  if [[ -e /dev/snd ]]; then ok "Host /dev/snd exists"; else warn "Host /dev/snd missing"; fi
  if curl -fsS --max-time 3 "$OLLAMA_URL/api/tags" >/dev/null; then ok "Ollama reachable"; else warn "Ollama not reachable at $OLLAMA_URL"; fi

  local state
  state="$(container_state)"
  if [[ "$state" == "running" ]]; then
    ok "Container $CONTAINER_NAME is running"
    curl -fsS --max-time 3 "$API_STATUS_URL" >/dev/null && ok "Flask API reachable" || warn "Flask API not reachable"
    (echo >"/dev/tcp/$RTSP_HOST/$RTSP_PORT") >/dev/null 2>&1 && ok "RTSP TCP port open" || warn "RTSP TCP port not open"
    curl -fsS --max-time 3 "$HLS_URL" >/dev/null && ok "HLS manifest reachable" || warn "HLS manifest not reachable"
    curl -fsS --max-time 3 "$API_VIDEO_DEVICES_URL" >/dev/null && ok "Video device API reachable" || warn "Video device API not reachable"
    curl -fsS --max-time 3 "$API_AUDIO_DEVICES_URL" >/dev/null && ok "Audio device API reachable" || warn "Audio device API not reachable"
  else
    warn "Container $CONTAINER_NAME state: $state"
  fi
}

down_stack() {
  step "Stopping Compose stack"
  compose down --remove-orphans
  ok "Compose stack stopped"
}

destroy_stack() {
  step "Stopping stack and removing local Compose image"
  compose down --remove-orphans --rmi local
  ok "Compose containers and local image removed"
}

show_logs() {
  compose logs -f "$SERVICE_NAME"
}

usage() {
  cat <<EOF
Usage:
  ./run.sh up [--follow] [--no-ngrok] [--no-build]
  ./run.sh restart [--follow] [--no-ngrok] [--no-build]
  ./run.sh down_up [--follow] [--no-ngrok] [--no-build]
  ./run.sh rebuild [--follow] [--no-ngrok]
  ./run.sh status
  ./run.sh logs
  ./run.sh down
  ./run.sh destroy

Notes:
  up       checks Docker, NVIDIA runtime, /dev/video0, /dev/snd, Ollama, container, API, RTSP, HLS, and device APIs.
  restart  runs docker compose down --remove-orphans before starting again.
  down_up  alias of restart for operators who want an explicit down-then-up command.
  rebuild  rebuilds the image with --no-cache before starting.
EOF
}

case "$MODE" in
  up)
    bring_up
    ;;
  restart)
    restart_stack
    ;;
  down_up)
    restart_stack
    ;;
  rebuild)
    rebuild_stack
    ;;
  status)
    status_stack
    ;;
  logs)
    show_logs
    ;;
  down|stop)
    down_stack
    ;;
  destroy)
    destroy_stack
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
