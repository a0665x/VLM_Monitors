#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ -x temp/v4l-package/root/usr/bin/v4l2-ctl ]]; then export PATH="$PWD/temp/v4l-package/root/usr/bin:$PATH"; fi
exec .venv/bin/gunicorn --workers 1 --threads 8 --timeout 180 --graceful-timeout 5 \
  --bind "${SERVICE_BIND:-127.0.0.1:5000}" --access-logfile - --error-logfile - src.wsgi:app
