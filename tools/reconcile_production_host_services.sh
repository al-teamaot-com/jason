#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <source-revision>" >&2
  exit 64
fi

SOURCE_REVISION="$1"
REPO_ROOT="/home/al/.local/lib/jason/engineering-source-repo"
RELEASE_ROOT="/opt/jason/releases"
RELEASE_DIR="$RELEASE_ROOT/$SOURCE_REVISION"
CURRENT_LINK="/opt/jason/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/backups/jason-systemd-$STAMP"
ENGINEERING_SOURCE_REPO="/home/al/.local/lib/jason/engineering-source-repo"
DOCUMENTATION_SOURCE_REPO="/home/al/.local/lib/jason/documentation-source-repo"
OBSERVABILITY_CURRENT_LINK="/opt/jason/observability/current"
USER_XDG_RUNTIME_DIR="/run/user/1000"
USER_DBUS_ADDRESS="unix:path=/run/user/1000/bus"


EXPORTER_UNITS=(
  jason-client-posture-exporter.service
  jason-playbook-exporter.service
  jason-production-health-exporter.service
  jason-operations-configuration-exporter.service
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
)
DEFERRED_MAINTENANCE_SERVICES=(
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
  operations_configuration_exporter.py
  resolution_memory_exporter.py
  reflection_exporter.py
  security_control_exporter.py
  status_exporter.py
  usage_attribution_exporter_runtime.py
  usage_exporter.py
)
VERIFY_PORTS=(9464 9465 9466 9467 9468 9470 9471 9472 9476 9477)

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: root privileges are required for systemd reconciliation." >&2
  exit 77
fi

DEVELOPER_CHECKOUT_PATH="/home/al/projects""/jason"
if grep -Fq "$DEVELOPER_CHECKOUT_PATH" "$0"; then
  echo "ERROR: production reconciliation script contains a developer checkout dependency" >&2
  exit 9
fi
if [ "$REPO_ROOT" != "/home/al/.local/lib/jason/engineering-source-repo" ]; then
  echo "ERROR: production reconciliation is not using the managed engineering source" >&2
  exit 9
fi
if [ "$DOCUMENTATION_SOURCE_REPO" != "/home/al/.local/lib/jason/documentation-source-repo" ]; then
  echo "ERROR: production reconciliation is not using the managed documentation source" >&2
  exit 9
fi

run_as_al() {
  runuser -u al -- env \
    HOME=/home/al \
    XDG_RUNTIME_DIR="$USER_XDG_RUNTIME_DIR" \
    DBUS_SESSION_BUS_ADDRESS="$USER_DBUS_ADDRESS" \
    PATH=/usr/local/bin:/usr/bin:/bin \
    "$@"
}

STEP_NAME=""
STEP_STARTED_AT=0
step_start() {
  STEP_NAME="$1"
  STEP_STARTED_AT="$(date +%s)"
  echo "HOST_RECONCILE_STEP_START=$STEP_NAME"
}
step_pass() {
  local finished
  finished="$(date +%s)"
  echo "HOST_RECONCILE_STEP_PASS=$1 duration_seconds=$((finished - STEP_STARTED_AT))"
}

verify_exporter_port() {
  local port="$1"
  local attempt
  for attempt in 1 2 3; do
    if curl --connect-timeout 2 --max-time 15 -fsS "http://127.0.0.1:$port/metrics" >/dev/null; then
      return 0
    fi
    if [ "$attempt" -lt 3 ]; then
      sleep 2
    fi
  done
  return 1
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
step_start managed_source_reconciliation
prepare_managed_clone "$ENGINEERING_SOURCE_REPO"
prepare_managed_clone "$DOCUMENTATION_SOURCE_REPO"
step_pass managed_source_reconciliation
if [ ! -d "$DOCUMENTATION_SOURCE_REPO/.git" ]; then
  echo "ERROR: managed documentation Git source was not materialized before unit activation." >&2
  exit 9
fi

for unit in "${EXPORTER_UNITS[@]}" "${MAINTENANCE_SERVICES[@]}" "${DEFERRED_MAINTENANCE_SERVICES[@]}" "${MAINTENANCE_TIMERS[@]}" "$PROVIDER_CANARY_SERVICE" "$PROVIDER_CANARY_TIMER" "${OBSOLETE_UNITS[@]}"; do
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

for unit in "${MAINTENANCE_SERVICES[@]}" "${DEFERRED_MAINTENANCE_SERVICES[@]}" "${MAINTENANCE_TIMERS[@]}"; do
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

step_start system_service_activation
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
timeout --signal=TERM --kill-after=5s 45s systemctl start "$PROVIDER_CANARY_SERVICE"
for unit in "${MAINTENANCE_SERVICES[@]}"; do
  timeout --signal=TERM --kill-after=5s 120s systemctl start "$unit"
done
systemctl reset-failed
step_pass system_service_activation

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
step_start exporter_verification
for port in "${VERIFY_PORTS[@]}"; do
  verify_exporter_port "$port" || {
    echo "ERROR: exporter verification failed on port $port after 3 bounded attempts" >&2
    exit 5
  }
done
step_pass exporter_verification
for unit in "${EXPORTER_UNITS[@]}" "${MAINTENANCE_SERVICES[@]}" "${DEFERRED_MAINTENANCE_SERVICES[@]}" "$PROVIDER_CANARY_SERVICE"; do
  wd="$(systemctl show "$unit" -p WorkingDirectory --value)"
  ex="$(systemctl show "$unit" -p ExecStart --value)"
  if printf '%s %s' "$wd" "$ex" | grep -qE '/home/al/(projects/jason|jason-worktrees/)'; then
    echo "ERROR: developer checkout dependency remains in $unit" >&2
    exit 6
  fi
done

# A production release is not complete until scheduled user-level workers and the
# self-heal watchdog are installed from the exact same SHA and their timers are live.
step_start user_worker_reconciliation
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
cmp -s "$ENGINEERING_SOURCE_REPO/tools/issue_resolution_engine.py" /home/al/.local/lib/jason/issue_resolution_engine.py || {
  echo "ERROR: installed issue-resolution engine differs from production source" >&2
  exit 9
}
for timer in jason-support-repair-worker.timer jason-self-heal-watchdog.timer; do
  if [ "$(run_as_al systemctl --user is-active "$timer" 2>/dev/null || true)" != "active" ]; then
    echo "ERROR: required user timer is not active after production install: $timer" >&2
    exit 9
  fi
done

# Reconcile the KFS toner exporter from the exact immutable production release.
step_start toner_exporter_reconciliation
TONER_UNIT_SOURCE="$RELEASE_DIR/infrastructure/showcase/systemd/jason-toner-exporter.service"
TONER_UNIT_DEST="/home/al/.config/systemd/user/jason-toner-exporter.service"
if [ ! -f "$TONER_UNIT_SOURCE" ]; then
  echo "ERROR: production toner exporter unit is missing from release" >&2
  exit 9
fi
run_as_al install -d -m 0755 /home/al/.config/systemd/user
run_as_al install -m 0644 "$TONER_UNIT_SOURCE" "$TONER_UNIT_DEST"
run_as_al systemctl --user daemon-reload
run_as_al systemctl --user enable --now jason-toner-exporter.service
TONER_WD="$(run_as_al systemctl --user show jason-toner-exporter.service -p WorkingDirectory --value)"
TONER_EXEC="$(run_as_al systemctl --user show jason-toner-exporter.service -p ExecStart --value)"
if printf '%s %s' "$TONER_WD" "$TONER_EXEC" | grep -qE '/home/al/(projects/jason|jason-worktrees/)'; then
  echo "ERROR: toner exporter retains developer checkout dependency" >&2
  exit 9
fi
if ! printf '%s %s' "$TONER_WD" "$TONER_EXEC" | grep -q '/opt/jason/current/infrastructure/toner-intelligence'; then
  echo "ERROR: toner exporter is not bound to immutable production source" >&2
  exit 9
fi
verify_exporter_port 9473 || {
  echo "ERROR: toner exporter verification failed on port 9473" >&2
  exit 9
}
step_pass toner_exporter_reconciliation
echo "JASON_TONER_EXPORTER_RECONCILIATION=PASS"

step_pass user_worker_reconciliation
echo "JASON_USER_WORKER_RECONCILIATION=PASS"
echo "ENGINEERING_SOURCE_REPO=$ENGINEERING_SOURCE_REPO"
echo "DOCUMENTATION_SOURCE_REPO=$DOCUMENTATION_SOURCE_REPO"

# Keep the privileged host-reconciliation boundary on the exact production
# implementation after this successful reconciliation. The worker validates
# only local refs from the managed engineering Git source.
step_start root_reconciler_install
/usr/bin/python3 "$RELEASE_DIR/tools/install_release_host_reconciler.py"
cmp -s "$RELEASE_DIR/tools/release_host_reconcile_worker.py" /usr/local/lib/jason/release_host_reconcile_worker.py || {
  echo "ERROR: installed root host reconciler differs from production source" >&2
  exit 9
}
if [ "$(systemctl is-active jason-release-host-reconcile.path 2>/dev/null || true)" != "active" ]; then
  echo "ERROR: root host-reconcile path is not active after production install" >&2
  exit 9
fi
step_pass root_reconciler_install
echo "JASON_ROOT_HOST_RECONCILER_RECONCILIATION=PASS"
echo "JASON_HOST_SERVICE_RECONCILIATION=PASS"
echo "HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION=$SOURCE_REVISION"
echo "MANAGED_ENGINEERING_SOURCE=PASS"
echo "MANAGED_DOCUMENTATION_SOURCE=PASS"
echo "DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT"
echo "SOURCE_REVISION=$SOURCE_REVISION"
echo "RELEASE_DIR=$RELEASE_DIR"
echo "BACKUP_DIR=$BACKUP_DIR"

OBSERVABILITY_INSTALLER="$RELEASE_DIR/tools/install_observability_assurance.sh"
OBSERVABILITY_PREVIOUS_REVISION=""
if [ -f "$OBSERVABILITY_CURRENT_LINK/SOURCE_REVISION" ]; then
  OBSERVABILITY_PREVIOUS_REVISION="$(tr -d '\r\n' < "$OBSERVABILITY_CURRENT_LINK/SOURCE_REVISION")"
fi
OBSERVABILITY_CHANGED=1
if [ -n "$OBSERVABILITY_PREVIOUS_REVISION" ] \
  && git -C "$REPO_ROOT" cat-file -e "$OBSERVABILITY_PREVIOUS_REVISION^{commit}" 2>/dev/null; then
  if git -C "$REPO_ROOT" diff --quiet \
    "$OBSERVABILITY_PREVIOUS_REVISION" "$SOURCE_REVISION" -- \
    config/observability/grafana-dashboard-manifest.json \
    infrastructure/showcase \
    tools/grafana_assurance.py \
    tools/update_grafana_manifest.py \
    tools/install_observability_assurance.sh; then
    OBSERVABILITY_CHANGED=0
  fi
fi
step_start observability_reconciliation
if [ "$OBSERVABILITY_CHANGED" -eq 1 ]; then
  test -f "$OBSERVABILITY_INSTALLER" || { echo "ERROR: observability installer is missing" >&2; exit 9; }
  timeout --signal=TERM --kill-after=5s 180s env JASON_REPO_ROOT="$ENGINEERING_SOURCE_REPO" /usr/bin/bash "$OBSERVABILITY_INSTALLER" "$SOURCE_REVISION"
  if [ "$(readlink -f "$OBSERVABILITY_CURRENT_LINK")" != "/opt/jason/observability/releases/$SOURCE_REVISION" ]; then
    echo "ERROR: observability release did not converge to production revision" >&2
    exit 9
  fi
  echo "JASON_OBSERVABILITY_RECONCILIATION=PASS"
else
  echo "JASON_OBSERVABILITY_RECONCILIATION=UNCHANGED"
fi
step_pass observability_reconciliation

# Documentation/control-board publication is deliberately outside the privileged
# host-alignment transaction. Release Manager performs it after runtime, MCP,
# immutable host, workers, and observability have aligned to the exact SHA.
echo "POST_SUCCESS_DOCUMENTATION_RECONCILIATION=DEFERRED_TO_RELEASE_MANAGER"
