#!/bin/sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME=/home/al/jason-runtime-tools/kfs
EVIDENCE=/home/al/jason-evidence/kfs-runs
SYSTEMD=/home/al/.config/systemd/user

install -d -m 0700 "$RUNTIME" "$EVIDENCE" "$SYSTEMD"
install -m 0700 "$HERE/kfs_collector.py" "$RUNTIME/kfs_collector.py"
install -m 0700 "$HERE/container_run_kfs.py" "$RUNTIME/container_run_kfs.py"
install -m 0700 "$HERE/run_kfs_collector_container.sh" "$RUNTIME/run_kfs_collector_container.sh"
install -m 0600 "$HERE/systemd/jason-kfs-collector.service" "$SYSTEMD/jason-kfs-collector.service"
install -m 0600 "$HERE/systemd/jason-kfs-collector.timer" "$SYSTEMD/jason-kfs-collector.timer"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
systemctl --user daemon-reload

if [ "${1:-}" = "--enable" ]; then
  systemctl --user enable --now jason-kfs-collector.timer
  systemctl --user status jason-kfs-collector.timer --no-pager
else
  echo "KFS collector installed but timer remains disabled."
  echo "Enable only after OpenBao/live-provider validation succeeds:"
  echo "  systemctl --user enable --now jason-kfs-collector.timer"
fi
