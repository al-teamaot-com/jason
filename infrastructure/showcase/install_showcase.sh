#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${JASON_REPO_ROOT:-$HOME/projects/jason}"
SHOWCASE_DIR="$REPO_ROOT/infrastructure/showcase"
SERVICE_SRC="$SHOWCASE_DIR/systemd/jason-status-exporter.service"
SERVICE_DST="/etc/systemd/system/jason-status-exporter.service"
ENV_FILE="$SHOWCASE_DIR/.env"

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
EOF
  echo "Created $ENV_FILE with mode 600."
fi
chmod 600 "$ENV_FILE"

sudo install -m 0644 "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable --now jason-status-exporter.service

cd "$SHOWCASE_DIR"
docker compose --env-file .env pull
docker compose --env-file .env up -d

echo
printf 'Grafana: http://%s:3000\n' "$(hostname -I | awk '{print $1}')"
printf 'Grafana admin user: '
grep '^GRAFANA_ADMIN_USER=' .env | cut -d= -f2-
printf 'Grafana admin password: '
grep '^GRAFANA_ADMIN_PASSWORD=' .env | cut -d= -f2-
echo

echo "Status exporter: http://127.0.0.1:9464/metrics"
echo "Prometheus: http://127.0.0.1:9090"
