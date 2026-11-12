#!/bin/sh
# Source-only installer. Does NOT enable or start the readback timer.
set -eu
[ "$#" -eq 0 ] || { echo "No activation arguments are supported" >&2; exit 2; }
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SYSTEMD=/home/al/.config/systemd/user
install -d -m 0700 "$SYSTEMD"
install -m 0600 "$HERE/systemd/jason-constant-contact-reconcile.service" "$SYSTEMD/jason-constant-contact-reconcile.service"
install -m 0600 "$HERE/systemd/jason-constant-contact-reconcile.timer" "$SYSTEMD/jason-constant-contact-reconcile.timer"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
systemctl --user daemon-reload
echo "Constant Contact readback units installed; timer NOT enabled or started."
echo "Activation requires a separately verified exact-SHA production release, live OAuth/consent acceptance, and host drift authorization."
