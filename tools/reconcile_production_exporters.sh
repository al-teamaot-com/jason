#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <source-revision>" >&2
  exit 64
fi

SOURCE_REVISION="$1"
REPO_ROOT="/home/al/projects/jason"
RELEASE_ROOT="/opt/jason/releases"
RELEASE_DIR="$RELEASE_ROOT/$SOURCE_REVISION"
CURRENT_LINK="/opt/jason/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/backups/jason-systemd-$STAMP"

ACTIVE_UNITS=(
  jason-client-posture-exporter.service
  jason-playbook-exporter.service
  jason-production-health-exporter.service
  jason-resolution-memory-exporter.service
  jason-security-control-exporter.service
  jason-status-exporter.service
  jason-usage-attribution-exporter.service
  jason-usage-exporter.service
)

OBSOLETE_UNITS=(
  jason-communication-template-exporter.service
  jason-completion-gap-exporter.service
  jason-component-engineering-exporter.service
  jason-prompt-exporter.service
)

EXPORTER_SCRIPTS=(
  client_posture_exporter.py
  playbook_exporter.py
  production_health_exporter.py
  resolution_memory_exporter.py
  security_control_exporter.py
  status_exporter.py
  usage_attribution_exporter_runtime.py
  usage_exporter.py
)

VERIFY_PORTS=(9464 9465 9466 9467 9468 9470 9471 9472)

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: root privileges are required for systemd reconciliation." >&2
  exit 77
fi

if ! git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}" 2>/dev/null; then
  git -C "$REPO_ROOT" fetch origin "$SOURCE_REVISION"
fi
git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}"

mkdir -p "$RELEASE_ROOT" "$BACKUP_DIR"

if [ ! -d "$RELEASE_DIR" ]; then
  TMP_RELEASE="$RELEASE_ROOT/.${SOURCE_REVISION}.tmp.$$"
  rm -rf "$TMP_RELEASE"
  mkdir -p "$TMP_RELEASE"
  git -C "$REPO_ROOT" archive "$SOURCE_REVISION" | tar -x -C "$TMP_RELEASE"
  chown -R root:root "$TMP_RELEASE"
  mv "$TMP_RELEASE" "$RELEASE_DIR"
fi

for unit in "${ACTIVE_UNITS[@]}" "${OBSOLETE_UNITS[@]}"; do
  if [ -f "/etc/systemd/system/$unit" ]; then
    cp -a "/etc/systemd/system/$unit" "$BACKUP_DIR/$unit.before"
  fi
done

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

for unit in "${ACTIVE_UNITS[@]}"; do
  src="$RELEASE_DIR/infrastructure/showcase/systemd/$unit"
  if [ ! -f "$src" ]; then
    echo "ERROR: missing canonical unit template: $src" >&2
    exit 2
  fi
  install -o root -g root -m 0644 "$src" "/etc/systemd/system/$unit"
done

for unit in "${OBSOLETE_UNITS[@]}"; do
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$unit"
done

systemctl daemon-reload

for unit in "${ACTIVE_UNITS[@]}"; do
  systemctl stop "$unit" >/dev/null 2>&1 || true
done

for script_name in "${EXPORTER_SCRIPTS[@]}"; do
  mapfile -t pids < <(pgrep -u al -f "$script_name" || true)
  for pid in "${pids[@]}"; do
    [ -n "$pid" ] || continue
    kill "$pid" >/dev/null 2>&1 || true
  done
done

sleep 1

for unit in "${ACTIVE_UNITS[@]}"; do
  systemctl enable --now "$unit"
done

systemctl reset-failed

for unit in "${ACTIVE_UNITS[@]}"; do
  if [ "$(systemctl is-active "$unit")" != "active" ]; then
    echo "ERROR: $unit is not active after reconciliation." >&2
    systemctl status "$unit" --no-pager -l || true
    exit 3
  fi
done

for unit in "${OBSOLETE_UNITS[@]}"; do
  state="$(systemctl is-active "$unit" 2>/dev/null || true)"
  if [ "$state" = "active" ] || [ "$state" = "activating" ]; then
    echo "ERROR: obsolete unit still active: $unit" >&2
    exit 4
  fi
done

for port in "${VERIFY_PORTS[@]}"; do
  if ! curl -fsS "http://127.0.0.1:$port/metrics" >/dev/null; then
    echo "ERROR: exporter verification failed on port $port" >&2
    exit 5
  fi
done

echo "JASON_EXPORTER_RECONCILIATION=PASS"
echo "SOURCE_REVISION=$SOURCE_REVISION"
echo "RELEASE_DIR=$RELEASE_DIR"
echo "BACKUP_DIR=$BACKUP_DIR"
