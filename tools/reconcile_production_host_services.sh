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
ENGINEERING_SOURCE_REPO="/home/al/.local/lib/jason/engineering-source-repo"
DOCUMENTATION_SOURCE_REPO="/home/al/.local/lib/jason/documentation-source-repo"
USER_XDG_RUNTIME_DIR="/run/user/1000"
USER_DBUS_ADDRESS="unix:path=/run/user/1000/bus"

EXPORTER_UNITS=(
  jason-client-posture-exporter.service
  jason-playbook-exporter.service
  jason-production-health-exporter.service
  jason-resolution-memory-exporter.service
  jason-reflection-exporter.service
  jason-security-control-exporter.service
  jason-status-exporter.service
  jason-usage-attribution-exporter.service
  jason-usage-exporter.service
)
MAINTENANCE_SERVICES=(
  jason-delegation-maintenance.service
  jason-openclaw-authority-health.service
  jason-documentation-reconciliation.service
)
MAINTENANCE_TIMERS=(
  jason-delegation-maintenance.timer
  jason-openclaw-authority-health.timer
  jason-documentation-reconciliation.timer
)
PROVIDER_CANARY_SERVICE=jason-provider-health-canary.service
PROVIDER_CANARY_TIMER=jason-provider-health-canary.timer
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
  reflection_exporter.py
  security_control_exporter.py
  status_exporter.py
  usage_attribution_exporter_runtime.py
  usage_exporter.py
)
VERIFY_PORTS=(9464 9465 9466 9467 9468 9470 9471 9472 9476)

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: root privileges are required for systemd reconciliation." >&2
  exit 77
fi

run_as_al() {
  runuser -u al -- env \
    HOME=/home/al \
    XDG_RUNTIME_DIR="$USER_XDG_RUNTIME_DIR" \
    DBUS_SESSION_BUS_ADDRESS="$USER_DBUS_ADDRESS" \
    PATH=/usr/local/bin:/usr/bin:/bin \
    "$@"
}

wait_user_unit_inactive() {
  local unit="$1"
  local attempt
  for attempt in $(seq 1 90); do
    state="$(run_as_al systemctl --user is-active "$unit" 2>/dev/null || true)"
    if [ "$state" != "active" ] && [ "$state" != "activating" ]; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: user unit did not become inactive before production install: $unit" >&2
  return 1
}

if ! git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}" 2>/dev/null; then
  git -C "$REPO_ROOT" fetch origin "$SOURCE_REVISION"
fi
git -C "$REPO_ROOT" cat-file -e "$SOURCE_REVISION^{commit}"

LIVE_MCP_REVISION="$(docker inspect jason-mcp-pilot --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
if [ "$LIVE_MCP_REVISION" != "$SOURCE_REVISION" ]; then
  echo "ERROR: live MCP revision does not match requested host release." >&2
  echo "LIVE_MCP_REVISION=$LIVE_MCP_REVISION" >&2
  echo "REQUESTED_SOURCE_REVISION=$SOURCE_REVISION" >&2
  exit 7
fi

mkdir -p "$RELEASE_ROOT" "$BACKUP_DIR" /var/lib/jason
printf 'JASON_EXPECTED_MCP_SOURCE_REVISION=%s\n' "$SOURCE_REVISION" > /var/lib/jason/production-health.env
chown root:root /var/lib/jason/production-health.env
chmod 0644 /var/lib/jason/production-health.env
if [ ! -d "$RELEASE_DIR" ]; then
  TMP_RELEASE="$RELEASE_ROOT/.${SOURCE_REVISION}.tmp.$$"
  rm -rf "$TMP_RELEASE"
  mkdir -p "$TMP_RELEASE"
  git -C "$REPO_ROOT" archive "$SOURCE_REVISION" | tar -x -C "$TMP_RELEASE"
  chown -R root:root "$TMP_RELEASE"
  mv "$TMP_RELEASE" "$RELEASE_DIR"
fi
chown root:root "$RELEASE_DIR"
chmod 0755 "$RELEASE_DIR"

# User-level engineering/release and documentation automation need writable Git
# metadata, while runtime artifacts need the immutable /opt release. Maintain
# dedicated managed clones rather than depending on a developer checkout.
REMOTE_URL="$(git -C "$REPO_ROOT" remote get-url origin)"
prepare_managed_clone() {
  local destination="$1"
  install -d -o al -g al -m 0755 "$(dirname "$destination")"
  if [ ! -d "$destination/.git" ]; then
    if [ -e "$destination" ]; then
      echo "ERROR: managed Git source exists but is not a repository: $destination" >&2
      exit 9
    fi
    run_as_al git clone --no-hardlinks "$REPO_ROOT" "$destination"
  fi
  if [ -n "$(run_as_al git -C "$destination" status --porcelain)" ]; then
    echo "ERROR: managed Git source is dirty: $destination" >&2
    exit 9
  fi
  run_as_al git -C "$destination" remote set-url origin "$REMOTE_URL"
  run_as_al git -C "$destination" fetch --no-tags origin main
  run_as_al git -C "$destination" checkout --detach "$SOURCE_REVISION"
  if [ "$(run_as_al git -C "$destination" rev-parse HEAD)" != "$SOURCE_REVISION" ]; then
    echo "ERROR: managed Git source revision does not match production: $destination" >&2
    exit 9
  fi
}
prepare_managed_clone "$ENGINEERING_SOURCE_REPO"
prepare_managed_clone "$DOCUMENTATION_SOURCE_REPO"
if [ ! -d "$DOCUMENTATION_SOURCE_REPO/.git" ]; then
  echo "ERROR: managed documentation Git source was not materialized before unit activation." >&2
  exit 9
fi

for unit in "${EXPORTER_UNITS[@]}" "${MAINTENANCE_SERVICES[@]}" "${MAINTENANCE_TIMERS[@]}" "$PROVIDER_CANARY_SERVICE" "$PROVIDER_CANARY_TIMER" "${OBSOLETE_UNITS[@]}"; do
  if [ -f "/etc/systemd/system/$unit" ]; then
    cp -a "/etc/systemd/system/$unit" "$BACKUP_DIR/$unit.before"
  fi
done

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

for unit in "${EXPORTER_UNITS[@]}"; do
  src="$RELEASE_DIR/infrastructure/showcase/systemd/$unit"
  test -f "$src" || { echo "ERROR: missing canonical exporter unit: $src" >&2; exit 2; }
  install -o root -g root -m 0644 "$src" "/etc/systemd/system/$unit"
done

for unit in "${MAINTENANCE_SERVICES[@]}" "${MAINTENANCE_TIMERS[@]}"; do
  src="$RELEASE_DIR/infrastructure/openclaw-operations/systemd/$unit"
  test -f "$src" || { echo "ERROR: missing canonical maintenance unit: $src" >&2; exit 2; }
  install -o root -g root -m 0644 "$src" "/etc/systemd/system/$unit"
done
for unit in "$PROVIDER_CANARY_SERVICE" "$PROVIDER_CANARY_TIMER"; do
  src="$RELEASE_DIR/infrastructure/showcase/systemd/$unit"
  test -f "$src" || { echo "ERROR: missing canonical provider-canary unit: $src" >&2; exit 2; }
  install -o root -g root -m 0644 "$src" "/etc/systemd/system/$unit"
done

for unit in "${OBSOLETE_UNITS[@]}"; do
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$unit"
done

systemctl daemon-reload
for unit in "${EXPORTER_UNITS[@]}"; do
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
for unit in "${EXPORTER_UNITS[@]}"; do
  systemctl enable --now "$unit"
done
for timer in "${MAINTENANCE_TIMERS[@]}"; do
  systemctl enable --now "$timer"
done
systemctl enable --now "$PROVIDER_CANARY_TIMER"
systemctl start "$PROVIDER_CANARY_SERVICE"
for unit in "${MAINTENANCE_SERVICES[@]}"; do
  systemctl start "$unit"
done
systemctl reset-failed

for unit in "${EXPORTER_UNITS[@]}"; do
  if [ "$(systemctl is-active "$unit")" != "active" ]; then
    echo "ERROR: $unit is not active after reconciliation." >&2
    systemctl status "$unit" --no-pager -l || true
    exit 3
  fi
done
for timer in "${MAINTENANCE_TIMERS[@]}"; do
  if [ "$(systemctl is-active "$timer")" != "active" ]; then
    echo "ERROR: $timer is not active after reconciliation." >&2
    systemctl status "$timer" --no-pager -l || true
    exit 3
  fi
done
if [ "$(systemctl is-active "$PROVIDER_CANARY_TIMER")" != "active" ]; then
  echo "ERROR: $PROVIDER_CANARY_TIMER is not active after reconciliation." >&2
  systemctl status "$PROVIDER_CANARY_TIMER" --no-pager -l || true
  exit 3
fi
if [ "$(systemctl show "$PROVIDER_CANARY_SERVICE" -p Result --value)" != "success" ]; then
  echo "ERROR: $PROVIDER_CANARY_SERVICE did not complete successfully." >&2
  systemctl status "$PROVIDER_CANARY_SERVICE" --no-pager -l || true
  exit 3
fi
for unit in "${MAINTENANCE_SERVICES[@]}"; do
  if [ "$(systemctl show "$unit" -p Result --value)" != "success" ]; then
    echo "ERROR: $unit did not complete successfully." >&2
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
  curl -fsS "http://127.0.0.1:$port/metrics" >/dev/null || {
    echo "ERROR: exporter verification failed on port $port" >&2
    exit 5
  }
done
for unit in "${EXPORTER_UNITS[@]}" "${MAINTENANCE_SERVICES[@]}" "$PROVIDER_CANARY_SERVICE"; do
  wd="$(systemctl show "$unit" -p WorkingDirectory --value)"
  ex="$(systemctl show "$unit" -p ExecStart --value)"
  if printf '%s %s' "$wd" "$ex" | grep -qE '/home/al/(projects/jason|jason-worktrees/)'; then
    echo "ERROR: developer checkout dependency remains in $unit" >&2
    exit 6
  fi
done

# A production release is not complete until scheduled user-level workers and the
# self-heal watchdog are installed from the exact same SHA and their timers are live.
wait_user_unit_inactive jason-support-repair-worker.service
wait_user_unit_inactive jason-self-heal-watchdog.service
run_as_al /usr/bin/python3 "$ENGINEERING_SOURCE_REPO/tools/install_support_repair_host_worker.py" \
  --repo "$ENGINEERING_SOURCE_REPO" \
  --spool /var/lib/jason/openclaw/support-repair \
  --activate
run_as_al /usr/bin/python3 "$ENGINEERING_SOURCE_REPO/tools/install_self_heal_watchdog.py" \
  --repo "$ENGINEERING_SOURCE_REPO" \
  --root /var/lib/jason/openclaw/self-heal \
  --activate

ENGINEERING_SOURCE="$(readlink -f /home/al/.local/lib/jason/engineering-worker-source)"
if [ "$ENGINEERING_SOURCE" != "$ENGINEERING_SOURCE_REPO" ]; then
  echo "ERROR: engineering-worker-source does not match managed production Git source." >&2
  exit 9
fi
if [ "$(run_as_al git -C "$ENGINEERING_SOURCE" rev-parse HEAD)" != "$SOURCE_REVISION" ]; then
  echo "ERROR: engineering-worker-source revision does not match production." >&2
  exit 9
fi
for worker in \
  support_repair_host_worker.py \
  owner_approved_development_worker.py \
  todo_engineering_intake.py \
  todo_release_bridge.py \
  release_manager_gate.py; do
  cmp -s "$ENGINEERING_SOURCE_REPO/tools/$worker" "/home/al/.local/lib/jason/$worker" || {
    echo "ERROR: installed worker differs from production source: $worker" >&2
    exit 9
  }
done
cmp -s "$ENGINEERING_SOURCE_REPO/tools/jason_self_heal_watchdog.py" /home/al/.local/lib/jason/jason_self_heal_watchdog.py || {
  echo "ERROR: installed self-heal watchdog differs from production source" >&2
  exit 9
}
for timer in jason-support-repair-worker.timer jason-self-heal-watchdog.timer; do
  if [ "$(run_as_al systemctl --user is-active "$timer" 2>/dev/null || true)" != "active" ]; then
    echo "ERROR: required user timer is not active after production install: $timer" >&2
    exit 9
  fi
done

echo "JASON_USER_WORKER_RECONCILIATION=PASS"
echo "ENGINEERING_SOURCE_REPO=$ENGINEERING_SOURCE_REPO"
echo "DOCUMENTATION_SOURCE_REPO=$DOCUMENTATION_SOURCE_REPO"
echo "JASON_HOST_SERVICE_RECONCILIATION=PASS"
echo "SOURCE_REVISION=$SOURCE_REVISION"
echo "RELEASE_DIR=$RELEASE_DIR"
echo "BACKUP_DIR=$BACKUP_DIR"

DOC_PUBLISHER="$RELEASE_DIR/tools/publish_documentation_reconciliation.sh"
if [ ! -x "$DOC_PUBLISHER" ]; then
  echo "ERROR: post-success documentation publisher is missing: $DOC_PUBLISHER" >&2
  exit 8
fi
if ! runuser -u al -- env \
  HOME=/home/al \
  PATH=/usr/local/bin:/usr/bin:/bin \
  JASON_DOCUMENTATION_REPO_ROOT=/home/al/projects/jason \
  JASON_DOCUMENTATION_WORKTREE_ROOT=/home/al/jason-worktrees \
  bash "$DOC_PUBLISHER" production "$SOURCE_REVISION"; then
  echo "ERROR: production succeeded but documentation reconciliation publication failed" >&2
  exit 8
fi
echo "POST_SUCCESS_DOCUMENTATION_RECONCILIATION=PASS"
