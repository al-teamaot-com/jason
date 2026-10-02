#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "KFS install requires root." >&2
  exit 77
fi

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME=/opt/jason/services/kfs
EVIDENCE=/var/lib/jason/evidence/kfs-runs
SECRETS=/var/lib/jason/runtime-secrets/kfs
SYSTEMD=/etc/systemd/system

install -d -o jason -g jason -m 0750 "$RUNTIME" "$EVIDENCE"
install -d -o jason -g jason -m 0700 "$SECRETS"
install -m 0750 "$HERE/kfs_collector.py" "$RUNTIME/kfs_collector.py"
install -m 0750 "$HERE/container_run_kfs.py" "$RUNTIME/container_run_kfs.py"
install -m 0750 "$HERE/run_kfs_collector_container.sh" "$RUNTIME/run_kfs_collector_container.sh"
install -m 0644 "$HERE/systemd/jason-kfs-collector.service" "$SYSTEMD/jason-kfs-collector.service"
install -m 0644 "$HERE/systemd/jason-kfs-collector.timer" "$SYSTEMD/jason-kfs-collector.timer"

systemctl daemon-reload

if [ "${1:-}" = "--enable" ]; then
  systemctl enable --now jason-kfs-collector.timer
  systemctl status jason-kfs-collector.timer --no-pager
else
  echo "KFS collector installed but timer remains disabled."
  echo "Enable only after governed secret/image validation succeeds:"
  echo "  systemctl enable --now jason-kfs-collector.timer"
fi
