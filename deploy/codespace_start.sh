#!/usr/bin/env bash
# Starts the full AQI Truth stack inside a GitHub Codespace and makes port 8000 public.
# Runs automatically on every Codespace start (see .devcontainer/devcontainer.json); log: /tmp/aqi-start.log
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^DB2_PASSWORD=.*/DB2_PASSWORD=$(openssl rand -hex 12)/; s/^DB2_READER_PASSWORD=.*/DB2_READER_PASSWORD=$(openssl rand -hex 12)/" .env
  chmod 600 .env
fi
URL="https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
grep -q '^ALLOWED_ORIGINS=' .env || echo "ALLOWED_ORIGINS=https://debi910.github.io,${URL}" >> .env
until docker info >/dev/null 2>&1; do sleep 2; done
docker compose up -d --build
until [ "$(docker compose ps -a setup --format '{{.State}}')" = "exited" ]; do sleep 15; done
if [ ! -f data/.full_loaded ]; then
  docker compose run --rm -v "$PWD/data/raw:/app/data/raw" setup sh -c \
    "python scripts/fetch_openaq.py data/raw 2025 09,10,11,12 && python src/load.py data/raw 2025-09-01 2025-12-31" \
    && touch data/.full_loaded
  docker compose restart app
fi
gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" || echo "Set port 8000 to Public in the Ports tab"
echo "READY: $URL"
