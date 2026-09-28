#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${JASON_REPO_ROOT:-/home/al/projects/jason}"
UNIT_ROOT="$REPO_ROOT/infrastructure/openclaw-operations/systemd"
STATE_ROOT="/var/lib/jason/openclaw/support-intake"

cd "$REPO_ROOT"

required=(
  "$UNIT_ROOT/jason-support-intake.service"
  "$UNIT_ROOT/jason-support-intake.timer"
  "$REPO_ROOT/tools/jason_support_intake.py"
)

for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "[FAIL] Missing required file: $path" >&2
    exit 1
  fi
done

echo "========================================================================"
echo "PROJECT JASON - INSTALL NATIVE SUPPORT INTAKE"
echo "========================================================================"
echo "[PASS] Working directory: $REPO_ROOT"

sudo install -d -m 0700 -o al -g al "$STATE_ROOT"
sudo install -m 0644 "$UNIT_ROOT/jason-support-intake.service"   /etc/systemd/system/jason-support-intake.service
sudo install -m 0644 "$UNIT_ROOT/jason-support-intake.timer"   /etc/systemd/system/jason-support-intake.timer

sudo systemctl daemon-reload
sudo systemctl enable --now jason-support-intake.timer
sudo systemctl start jason-support-intake.service

state="$(systemctl is-active jason-support-intake.timer)"
if [[ "$state" != "active" ]]; then
  echo "[FAIL] jason-support-intake.timer is $state" >&2
  exit 1
fi

queue="$STATE_ROOT/support-work-queue.json"
next="$STATE_ROOT/next-support-work.json"
for path in "$queue" "$next"; do
  if [[ ! -f "$path" ]]; then
    echo "[FAIL] Expected support intake artifact missing: $path" >&2
    exit 1
  fi
  mode="$(stat -c '%a' "$path")"
  if [[ "$mode" != "600" ]]; then
    echo "[FAIL] $path mode is $mode; expected 600" >&2
    exit 1
  fi
done

echo "[PASS] jason-support-intake.timer active"
echo "[PASS] support-work-queue.json created mode=600"
echo "[PASS] next-support-work.json created mode=600"
echo "[PASS] Browser dependency: none"
echo "========================================================================"
