#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <source-revision> [material-review-json]" >&2
  exit 64
fi
SOURCE_REVISION="$1"
MATERIAL_REVIEW_FILE="${2:-}"
REPO_ROOT="/home/al/projects/jason"
RELEASE_ROOT="/opt/jason/ccc-releases"
RELEASE_DIR="$RELEASE_ROOT/$SOURCE_REVISION"
CURRENT_LINK="/opt/jason/ccc-current"
CONFIG_DIR="/var/lib/jason/ccc"
CONFIG_PATH="$CONFIG_DIR/ccc.json"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/backups/jason-ccc-$STAMP"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: root privileges are required to install the CCC scheduler." >&2
  exit 77
fi

if ! git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}" 2>/dev/null; then
  git -C "$REPO_ROOT" fetch origin "$SOURCE_REVISION"
fi
git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}"
mkdir -p "$RELEASE_ROOT" "$CONFIG_DIR" "$BACKUP_DIR" /home/al/Jason-Evidence/CCC /home/al/Jason-Recovery/CCC

if [ ! -d "$RELEASE_DIR" ]; then
  TMP_RELEASE="$RELEASE_ROOT/.${SOURCE_REVISION}.tmp.$$"
  rm -rf "$TMP_RELEASE"
  mkdir -p "$TMP_RELEASE"
  git -C "$REPO_ROOT" archive "$SOURCE_REVISION" | tar -x -C "$TMP_RELEASE"
  chown -R root:root "$TMP_RELEASE"
  mv "$TMP_RELEASE" "$RELEASE_DIR"
fi

test -f "$RELEASE_DIR/tools/run_ccc.py"
test -f "$RELEASE_DIR/infrastructure/ccc/systemd/jason-ccc.service"
test -f "$RELEASE_DIR/infrastructure/ccc/systemd/jason-ccc.timer"

for unit in jason-ccc.service jason-ccc.timer; do
  if [ -f "/etc/systemd/system/$unit" ]; then cp -a "/etc/systemd/system/$unit" "$BACKUP_DIR/$unit.before"; fi
done
if [ -f "$CONFIG_PATH" ]; then cp -a "$CONFIG_PATH" "$BACKUP_DIR/ccc.json.before"; fi

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"
install -o root -g root -m 0644 "$RELEASE_DIR/infrastructure/ccc/systemd/jason-ccc.service" /etc/systemd/system/jason-ccc.service
install -o root -g root -m 0644 "$RELEASE_DIR/infrastructure/ccc/systemd/jason-ccc.timer" /etc/systemd/system/jason-ccc.timer
if [ ! -f "$CONFIG_PATH" ]; then
  install -o al -g al -m 0600 "$RELEASE_DIR/config/ccc/default.json" "$CONFIG_PATH"
fi
chown al:al /var/lib/jason/ccc /home/al/Jason-Evidence/CCC /home/al/Jason-Recovery/CCC
chmod 0700 /var/lib/jason/ccc

if [ -n "$MATERIAL_REVIEW_FILE" ]; then
  test -f "$MATERIAL_REVIEW_FILE" || { echo "ERROR: material review file not found: $MATERIAL_REVIEW_FILE" >&2; exit 5; }
  python3 - "$MATERIAL_REVIEW_FILE" "$SOURCE_REVISION" <<'PYREVIEW'
import json,sys
from pathlib import Path
path=Path(sys.argv[1]); revision=sys.argv[2]
value=json.loads(path.read_text(encoding='utf-8'))
if value.get('status')!='approved' or value.get('source_revision')!=revision:
    raise SystemExit('material review must be approved and bound to the exact source revision')
PYREVIEW
  install -o al -g al -m 0600 "$MATERIAL_REVIEW_FILE" /var/lib/jason/ccc/material-review.json
fi

systemctl daemon-reload
systemctl enable --now jason-ccc.timer
systemctl start jason-ccc.service

if [ "$(systemctl is-active jason-ccc.timer)" != "active" ]; then
  echo "ERROR: jason-ccc.timer is not active" >&2
  exit 3
fi
result="$(systemctl show jason-ccc.service -p Result --value)"
if [ "$result" != "success" ]; then
  echo "ERROR: initial CCC service run did not complete successfully: $result" >&2
  systemctl status jason-ccc.service --no-pager -l || true
  exit 4
fi

echo "JASON_CCC_SCHEDULER_INSTALL=PASS"
echo "SOURCE_REVISION=$SOURCE_REVISION"
echo "RELEASE_DIR=$RELEASE_DIR"
echo "CONFIG_PATH=$CONFIG_PATH"
echo "BACKUP_DIR=$BACKUP_DIR"
