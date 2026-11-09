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
grep -q '^DB2_APP_PASSWORD=' .env || printf 'DB2_APP_USER=aqapp\nDB2_APP_PASSWORD=%s\n' "$(openssl rand -hex 12)" >> .env
sed -i "s/^DB2_APP_PASSWORD=change-me-app$/DB2_APP_PASSWORD=$(openssl rand -hex 12)/" .env
URL="https://${CODESPACE_NAME:-unknown}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
grep -q '^ALLOWED_ORIGINS=' .env || echo "ALLOWED_ORIGINS=https://debi910.github.io,${URL}" >> .env
until docker info >/dev/null 2>&1; do sleep 2; done
echo "docker ready"
# Second public route: a Cloudflare quick tunnel (no account, no card) for networks that block *.github.dev.
# Its random https://<words>.trycloudflare.com address goes to /tmp/tunnel.url; the keep-alive job publishes it
# on the 'endpoint' branch, where the GitHub Pages site looks for it.
if ! pgrep -x cloudflared >/dev/null; then
  [ -x /tmp/cloudflared ] || { curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared; } || true
  rm -f /tmp/tunnel.url   # a new tunnel gets a new address; never publish the old one
  [ -x /tmp/cloudflared ] && setsid nohup /tmp/cloudflared tunnel --no-autoupdate --protocol http2 --url http://localhost:8000 > /tmp/cloudflared.log 2>&1 < /dev/null &
fi
( for i in $(seq 1 60); do u=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -1); [ -n "$u" ] && { echo "$u" > /tmp/tunnel.url; break; }; sleep 2; done ) &
echo "starting compose"
docker compose up -d --build
until [ "$(docker compose ps -a setup --format '{{.State}}')" = "exited" ]; do sleep 15; done
# Existing Db2 containers predate the app user: create the OS users again (idempotent), then apply schema
# migrations (new triggers, indexes, views, grants) without touching loaded data.
docker compose up -d db2 >/dev/null   # picks up DB2_APP_PASSWORD if the container predates it
until docker compose exec -T db2 bash -c 'su - db2inst1 -c "db2 connect to ${DBNAME:-AQIDB}" >/dev/null'; do sleep 10; done
docker compose exec -T db2 bash /var/custom/01_reader.sh
docker compose run --rm setup python src/load.py data/sample 2025-10-01 2025-10-31 --if-empty --no-embed || true
# One-off after the 9 Nov 2026 method fixes: re-audit the loaded range with the new rules (appends new verdicts with
# receipts; the readings and their history are untouched), then refresh the Db2 evidence file.
if [ -f data/.full_loaded ] && [ ! -f data/.audit_v2 ]; then
  docker compose run --rm setup python src/load.py data/sample 2025-09-01 2025-12-31 --append --reaudit --no-embed && touch data/.audit_v2
  mkdir -p docs && docker compose run --rm -v "$PWD/docs:/app/docs" setup python scripts/db2_evidence.py || true
  docker compose up -d --force-recreate app
fi
if [ ! -f data/.full_loaded ]; then
  docker compose run --rm -v "$PWD/data/raw:/app/data/raw" setup sh -c \
    "python scripts/fetch_openaq.py data/raw 2025 09,10,11,12 && python src/load.py data/raw 2025-09-01 2025-12-31 --append" \
    && touch data/.full_loaded
  docker compose restart app
fi
[ -n "${CODESPACE_NAME:-}" ] && gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" 2>/dev/null || echo "port visibility is set by the keep-alive job"
echo "READY: $URL"
