#!/usr/bin/env bash
# Starts the full AQI Truth stack inside a GitHub Codespace and makes port 8000 public.
# Runs automatically on every Codespace start (see .devcontainer/devcontainer.json); log: /tmp/aqi-start.log
set -euo pipefail
echo $$ > /tmp/aqi-start.pid
cd "$(dirname "$0")/.."
echo "start $(date -u +%H:%M:%S)"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^DB2_PASSWORD=.*/DB2_PASSWORD=$(openssl rand -hex 12)/; s/^DB2_READER_PASSWORD=.*/DB2_READER_PASSWORD=$(openssl rand -hex 12)/" .env
  chmod 600 .env
fi
URL="https://${CODESPACE_NAME:-unknown}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
grep -q '^ALLOWED_ORIGINS=' .env || echo "ALLOWED_ORIGINS=https://debi910.github.io,${URL}" >> .env
until docker info >/dev/null 2>&1; do sleep 2; done
echo "docker ready"
# Second public route: a Cloudflare quick tunnel (no account, no card) for networks that block *.github.dev.
# Its random https://<words>.trycloudflare.com address goes to /tmp/tunnel.url; the keep-alive job publishes it
# on the 'endpoint' branch, where the GitHub Pages site looks for it.
if ! pgrep -x cloudflared >/dev/null; then
  [ -x /tmp/cloudflared ] || { curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared; } || true
  [ -x /tmp/cloudflared ] && setsid nohup /tmp/cloudflared tunnel --no-autoupdate --protocol http2 --url http://localhost:8000 > /tmp/cloudflared.log 2>&1 < /dev/null &
fi
( for i in $(seq 1 60); do u=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -1); [ -n "$u" ] && { echo "$u" > /tmp/tunnel.url; break; }; sleep 2; done ) &
echo "starting compose"
docker compose up -d --build
until [ "$(docker compose ps -a setup --format '{{.State}}')" = "exited" ]; do sleep 15; done
if [ ! -f data/.full_loaded ]; then
  docker compose run --rm -v "$PWD/data/raw:/app/data/raw" setup sh -c \
    "python scripts/fetch_openaq.py data/raw 2025 09,10,11,12 && python src/load.py data/raw 2025-09-01 2025-12-31" \
    && touch data/.full_loaded
  docker compose restart app
fi
[ -n "${CODESPACE_NAME:-}" ] && gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" 2>/dev/null || echo "port visibility is set by the keep-alive job"
echo "READY: $URL"
