#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${JASON_REPO_ROOT:-$HOME/projects/jason}"
SHOWCASE_DIR="$REPO_ROOT/infrastructure/showcase"
SERVICE_SRC="$SHOWCASE_DIR/systemd/jason-status-exporter.service"
SERVICE_DST="/etc/systemd/system/jason-status-exporter.service"
ENV_FILE="$SHOWCASE_DIR/.env"
DEFAULT_OLLAMA_MODEL="qwen3:1.7b"

cd "$REPO_ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  cat > "$ENV_FILE" <<EOF
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)
OLLAMA_MODEL=$DEFAULT_OLLAMA_MODEL
EOF
  echo "Created $ENV_FILE with mode 600."
fi

if ! grep -q '^OLLAMA_MODEL=' "$ENV_FILE"; then
  printf '\nOLLAMA_MODEL=%s\n' "$DEFAULT_OLLAMA_MODEL" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

OLLAMA_MODEL="$(grep '^OLLAMA_MODEL=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"

sudo install -m 0644 "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable --now jason-status-exporter.service

cd "$SHOWCASE_DIR"
docker compose --env-file .env pull
docker compose --env-file .env up -d

# Prometheus does not automatically reload its main configuration when the
# repository bind-mounted file changes. Restart Prometheus and Grafana so a
# repository update cannot leave the Command Center on stale scrape/dashboard
# configuration.
docker compose --env-file .env restart prometheus grafana

for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:9090/-/healthy >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "Prometheus did not become healthy after configuration reload." >&2
    exit 1
  fi
  sleep 2
done

for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "Grafana did not become healthy after configuration reload." >&2
    exit 1
  fi
  sleep 2
done

echo "Waiting for Ollama runtime..."
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "Ollama runtime did not become ready." >&2
    exit 1
  fi
  sleep 2
done

if ! docker exec jason-ollama ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$OLLAMA_MODEL"; then
  echo "Pulling local model: $OLLAMA_MODEL"
  docker exec jason-ollama ollama pull "$OLLAMA_MODEL"
else
  echo "Local model already present: $OLLAMA_MODEL"
fi

sudo systemctl restart jason-status-exporter.service

echo
printf 'Grafana: http://%s:3000\n' "$(hostname -I | awk '{print $1}')"
printf 'Grafana admin user: '
grep '^GRAFANA_ADMIN_USER=' .env | cut -d= -f2-
printf 'Grafana admin password: '
grep '^GRAFANA_ADMIN_PASSWORD=' .env | cut -d= -f2-
echo

echo "Status exporter: http://127.0.0.1:9464/metrics"
echo "Prometheus: http://127.0.0.1:9090"
echo "Ollama: http://127.0.0.1:11434"
echo "Local model: $OLLAMA_MODEL"
