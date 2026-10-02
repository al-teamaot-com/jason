#!/usr/bin/env bash
set -euo pipefail
# J-CHANGE-003 / #764: this legacy Production mutator is intentionally disabled
# until it is migrated behind the exact-plan Owner-approved promotion gate.
# Do not replace this with an environment-variable approval bypass.
echo "PRODUCTION_PROMOTION_GATE=BLOCKED legacy mutator is not an approved Production lane" >&2
echo "REASON=use the governed jason.deployment.apply promotion path after this component is migrated" >&2
exit 42

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <source-revision>" >&2
  exit 64
fi
SOURCE_REVISION="$1"
REPO_ROOT="/home/al/projects/jason"
OBS_ROOT="/opt/jason/observability"
RELEASE_DIR="$OBS_ROOT/releases/$SOURCE_REVISION"
CURRENT_LINK="$OBS_ROOT/current"
STATE_DIR="/var/lib/jason/observability"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/backups/jason-observability-$STAMP"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: root privileges are required" >&2
  exit 77
fi

git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}" 2>/dev/null || git -C "$REPO_ROOT" fetch origin "$SOURCE_REVISION"
git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}"
mkdir -p "$OBS_ROOT/releases" "$STATE_DIR" "$BACKUP_DIR"
chown al:al "$STATE_DIR"
chmod 0700 "$STATE_DIR"

if [ ! -d "$RELEASE_DIR" ]; then
  TMP="$OBS_ROOT/releases/.${SOURCE_REVISION}.tmp.$$"
  rm -rf "$TMP"; mkdir -p "$TMP"
  git -C "$REPO_ROOT" archive "$SOURCE_REVISION" | tar -x -C "$TMP"
  printf '%s\n' "$SOURCE_REVISION" > "$TMP/SOURCE_REVISION"
  chown -R root:root "$TMP"
  mv "$TMP" "$RELEASE_DIR"
fi

test -f "$RELEASE_DIR/SOURCE_REVISION"
test -f "$RELEASE_DIR/infrastructure/showcase/deploy_usage_dashboard.sh"
test -f "$RELEASE_DIR/config/observability/grafana-dashboard-manifest.json"
test -f "$RELEASE_DIR/tools/grafana_assurance.py"

OLD_CURRENT="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
printf 'old_current=%s\nnew_release=%s\n' "$OLD_CURRENT" "$RELEASE_DIR" > "$BACKUP_DIR/release-boundary.txt"
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

if ! JASON_REPO_ROOT="$RELEASE_DIR" \
JASON_USAGE_DEPLOY_BACKUP_DIR="$BACKUP_DIR/usage-deployment" \
  /usr/bin/bash "$RELEASE_DIR/infrastructure/showcase/deploy_usage_dashboard.sh"; then
  if [ -n "$OLD_CURRENT" ] && [ -d "$OLD_CURRENT" ]; then
    ln -sfn "$OLD_CURRENT" "$CURRENT_LINK"
  fi
  echo "ERROR: observability deployment acceptance failed; current pointer restored" >&2
  exit 1
fi

install -o root -g root -m 0644 "$CURRENT_LINK/infrastructure/showcase/systemd/jason-grafana-assurance.service" /etc/systemd/system/jason-grafana-assurance.service
install -o root -g root -m 0644 "$CURRENT_LINK/infrastructure/showcase/systemd/jason-grafana-assurance.timer" /etc/systemd/system/jason-grafana-assurance.timer
install -o root -g root -m 0644 "$CURRENT_LINK/infrastructure/showcase/systemd/jason-grafana-assurance-exporter.service" /etc/systemd/system/jason-grafana-assurance-exporter.service

install -o al -g al -m 0600 "$BACKUP_DIR/usage-deployment/grafana-assurance.json" "$STATE_DIR/grafana-assurance.json"
systemctl daemon-reload
systemctl enable --now jason-grafana-assurance-exporter.service jason-grafana-assurance.timer
systemctl start jason-grafana-assurance.service

systemctl is-active --quiet jason-grafana-assurance-exporter.service
systemctl is-active --quiet jason-grafana-assurance.timer
python3 - <<'PY'
import json
p='/var/lib/jason/observability/grafana-assurance.json'
d=json.load(open(p))
if d.get('status')!='PASS': raise SystemExit('Grafana assurance is not PASS')
print('GRAFANA_ASSURANCE='+d['status'])
print('REQUIRED_DASHBOARDS='+str(d.get('summary',{}).get('required_dashboards',0)))
print('METRIC_DEPENDENCIES='+str(d.get('summary',{}).get('metric_dependencies',0)))
PY

echo "JASON_OBSERVABILITY_INSTALL=PASS"
echo "SOURCE_REVISION=$SOURCE_REVISION"
echo "RELEASE_DIR=$RELEASE_DIR"
echo "CURRENT_LINK=$(readlink -f "$CURRENT_LINK")"
echo "BACKUP_DIR=$BACKUP_DIR"
