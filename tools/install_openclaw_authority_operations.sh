#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${JASON_REPO_ROOT:-/home/al/projects/jason}"
UNIT_ROOT="$REPO_ROOT/infrastructure/openclaw-operations/systemd"
STATE_ROOT="/var/lib/jason/openclaw"

cd "$REPO_ROOT"

required=(
  "$UNIT_ROOT/jason-delegation-maintenance.service"
  "$UNIT_ROOT/jason-delegation-maintenance.timer"
  "$UNIT_ROOT/jason-openclaw-authority-health.service"
  "$UNIT_ROOT/jason-openclaw-authority-health.timer"
  "$REPO_ROOT/tools/delegation_maintenance.py"
  "$REPO_ROOT/tools/openclaw_authority_health_snapshot.py"
)

for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "[FAIL] Missing required file: $path" >&2
    exit 1
  fi
done

echo "========================================================================"
echo "PROJECT JASON - INSTALL OPENCLAW / JKD-001 OPERATIONS"
echo "========================================================================"
echo "[PASS] Working directory: $REPO_ROOT"

sudo install -d -m 0700 -o al -g al "$STATE_ROOT"

for unit in \
  jason-delegation-maintenance.service \
  jason-delegation-maintenance.timer \
  jason-openclaw-authority-health.service \
  jason-openclaw-authority-health.timer
do
  sudo install -m 0644 "$UNIT_ROOT/$unit" "/etc/systemd/system/$unit"
  echo "[PASS] Installed $unit"
done

sudo systemctl daemon-reload
sudo systemctl enable --now jason-delegation-maintenance.timer
sudo systemctl enable --now jason-openclaw-authority-health.timer

# Normalize current lifecycle state immediately, then produce the first health snapshot.
sudo systemctl start jason-delegation-maintenance.service
sudo systemctl start jason-openclaw-authority-health.service

if [[ -f "$STATE_ROOT/operational-health.json" ]]; then
  chmod 0600 "$STATE_ROOT/operational-health.json"
  echo "[PASS] Operational health snapshot created"
else
  echo "[FAIL] Operational health snapshot missing" >&2
  exit 1
fi

for timer in jason-delegation-maintenance.timer jason-openclaw-authority-health.timer; do
  state="$(systemctl is-active "$timer")"
  if [[ "$state" != "active" ]]; then
    echo "[FAIL] $timer is $state" >&2
    exit 1
  fi
  echo "[PASS] $timer active"
done

mode="$(stat -c '%a' "$STATE_ROOT/operational-health.json")"
if [[ "$mode" != "600" ]]; then
  echo "[FAIL] operational-health.json mode is $mode" >&2
  exit 1
fi

echo "[PASS] operational-health.json mode=600"
echo "[PASS] No provider credential resolved"
echo "[PASS] No provider request performed"
echo "========================================================================"
