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
  jason-openclaw-authority-full-integrity.service
)
MAINTENANCE_TIMERS=(
  jason-delegation-maintenance.timer
  jason-openclaw-authority-health.timer
  jason-openclaw-authority-full-integrity.timer
  jason-documentation-reconciliation.timer
)
PROVIDER_CANARY_SERVICE=jason-provider-health-canary.service
PROVIDER_CANARY_TIMER=jason-provider-health-canary.timer
DRIFT_WATCHDOG_SERVICE=jason-production-drift-watchdog.service
DRIFT_WATCHDOG_TIMER=jason-production-drift-watchdog.timer
OBSOLETE_UNITS=(
  jason-communication-template-exporter.service
  jason-completion-gap-exporter.service
  jason-component-engineering-exporter.service
  jason-prompt-exporter.service
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

# Keep actionable failure evidence in the root reconciliation result rather
# than printing only the opaque start marker for a failed systemd command.
CURRENT_UNIT=""
on_host_reconcile_error() {
  local code=$?
  trap - ERR
  echo "HOST_RECONCILE_FAILURE step=${STEP_NAME:-unknown} unit=${CURRENT_UNIT:-none} rc=$code" >&2
  if [ -n "$CURRENT_UNIT" ]; then
    systemctl show "$CURRENT_UNIT" -p ActiveState -p SubState -p Result -p ExecMainStatus --no-pager >&2 || true
  fi
  exit "$code"
}
trap 'on_host_reconcile_error' ERR

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

# Root worker and audited rollback helper MUST be staged before any
# candidate-specific systemd unit is installed. A separately Owner/CCC-
# approved migration may temporarily declare the new timer ALLOWED but
# not yet REQUIRED. The full required timer is committed only after
# independent systemd activation checks pass near the end of this script.
step_start protected_root_policy_stage
/usr/bin/python3 "$RELEASE_DIR/tools/install_release_host_reconciler.py" --stage-only
cmp -s "$RELEASE_DIR/tools/protected_root_policy_migration.py" /usr/local/lib/jason/protected_root_policy_migration.py || {
  echo "ERROR: root policy migration helper differs from exact immutable release" >&2
  exit 9
}
cmp -s "$RELEASE_DIR/tools/release_host_reconcile_worker.py" /usr/local/lib/jason/release_host_reconcile_worker.py || {
  echo "ERROR: root host rollback worker differs from exact immutable release" >&2
  exit 9
}
step_pass protected_root_policy_stage

for unit in "${EXPORTER_UNITS[@]}" "${MAINTENANCE_SERVICES[@]}" "${DEFERRED_MAINTENANCE_SERVICES[@]}" "${MAINTENANCE_TIMERS[@]}" "$PROVIDER_CANARY_SERVICE" "$PROVIDER_CANARY_TIMER" "$DRIFT_WATCHDOG_SERVICE" "$DRIFT_WATCHDOG_TIMER" "${OBSOLETE_UNITS[@]}"; do
  if [ -f "/etc/systemd/system/$unit" ]; then
    cp -a "/etc/systemd/system/$unit" "$BACKUP_DIR/$unit.before"
  fi
done

# During a rollback, candidate-added Jason units can be absent from the
# previous immutable release manifest. Leaving them installed causes a real
# desired-state drift failure even if runtime/MCP and the host SHA align.
# Stage both plans before touching a unit. Compare exact candidate release
# bytes and bounded, declared delta; unknown/unmanaged changes fail closed.
step_start release_owned_unit_delta
PREVIOUS_HOST_RELEASE="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
if [ -n "$PREVIOUS_HOST_RELEASE" ] && [ "$PREVIOUS_HOST_RELEASE" != "$RELEASE_DIR" ]; then
  UNIT_DELTA_PLANNER="$RELEASE_DIR/tools/reconcile_managed_unit_delta.py"
  if [ ! -f "$UNIT_DELTA_PLANNER" ]; then
    echo "ERROR: immutable target release lacks the unit-delta safety planner" >&2
    exit 9
  fi
  SYSTEM_UNIT_DELTA="$BACKUP_DIR/release-system-unit-delta.txt"
  USER_UNIT_DELTA="$BACKUP_DIR/release-user-unit-delta.txt"
  if ! /usr/bin/python3 "$UNIT_DELTA_PLANNER" \
    --candidate "$PREVIOUS_HOST_RELEASE" --target "$RELEASE_DIR" \
    --scope system --installed-dir /etc/systemd/system > "$SYSTEM_UNIT_DELTA"; then
    echo "ERROR: cannot verify previous-release system-unit delta" >&2
    exit 9
  fi
  if ! /usr/bin/python3 "$UNIT_DELTA_PLANNER" \
    --candidate "$PREVIOUS_HOST_RELEASE" --target "$RELEASE_DIR" \
    --scope user --installed-dir /home/al/.config/systemd/user > "$USER_UNIT_DELTA"; then
    echo "ERROR: cannot verify previous-release user-unit delta" >&2
    exit 9
  fi

  # Unit names are validated by the immutable Python planner before emission.
  # Both system and user removals are part of this protected release transaction;
  # they may not be run as a standalone clean-up task.
  mapfile -t REMOVE_SYSTEM_UNITS < "$SYSTEM_UNIT_DELTA"
  mapfile -t REMOVE_USER_UNITS < "$USER_UNIT_DELTA"
  for unit in "${REMOVE_SYSTEM_UNITS[@]}"; do
    CURRENT_UNIT="$unit"
    cp -a "/etc/systemd/system/$unit" "$BACKUP_DIR/system-$unit.before"
    timeout --signal=TERM --kill-after=5s 45s systemctl disable --now "$unit"
    rm -f -- "/etc/systemd/system/$unit"
    if [ -e "/etc/systemd/system/$unit" ]; then
      echo "ERROR: candidate-only system unit not removed: $unit" >&2
      exit 9
    fi
  done
  for unit in "${REMOVE_USER_UNITS[@]}"; do
    CURRENT_UNIT="$unit"
    cp -a "/home/al/.config/systemd/user/$unit" "$BACKUP_DIR/user-$unit.before"
    timeout --signal=TERM --kill-after=5s 45s \
      runuser -u al -- env HOME=/home/al \
      XDG_RUNTIME_DIR="$USER_XDG_RUNTIME_DIR" \
      DBUS_SESSION_BUS_ADDRESS="$USER_DBUS_ADDRESS" \
      PATH=/usr/local/bin:/usr/bin:/bin systemctl --user disable --now "$unit"
    rm -f -- "/home/al/.config/systemd/user/$unit"
    if [ -e "/home/al/.config/systemd/user/$unit" ]; then
      echo "ERROR: candidate-only user unit not removed: $unit" >&2
      exit 9
    fi
  done
  if [ "${#REMOVE_SYSTEM_UNITS[@]}" -ne 0 ]; then
    systemctl daemon-reload
  fi
  if [ "${#REMOVE_USER_UNITS[@]}" -ne 0 ]; then
    run_as_al systemctl --user daemon-reload
  fi
  CURRENT_UNIT=""
  echo "JASON_RELEASE_UNIT_DELTA_REMOVED=system:${#REMOVE_SYSTEM_UNITS[@]},user:${#REMOVE_USER_UNITS[@]}"
else
  echo "JASON_RELEASE_UNIT_DELTA_REMOVED=not_applicable"
fi
step_pass release_owned_unit_delta

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

RECOVERY_PROFILE="$(/usr/bin/python3 - "$SOURCE_REVISION" <<'PY2'
import json, pathlib, sys
sha=sys.argv[1]
root=pathlib.Path('/var/lib/jason/openclaw/release-manager/records')
prefix='release-'+sha[:16]
matched=[]
for path in sorted(root.glob(prefix+'*.json')):
    try: doc=json.loads(path.read_text(encoding='utf-8'))
    except Exception: continue
    if ((doc.get('release_candidate') or {}).get('candidate_sha') == sha
            and doc.get('state') == 'production'):
        matched.append(str((doc.get('open_breaker_recovery') or {}).get('profile_id') or ''))
if len(matched) > 1: raise SystemExit('multiple production recovery records for exact candidate')
print(matched[0] if matched else '')
PY2
)"

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
for unit in "$DRIFT_WATCHDOG_SERVICE" "$DRIFT_WATCHDOG_TIMER"; do
  src="$RELEASE_DIR/infrastructure/openclaw-operations/systemd/$unit"
  test -f "$src" || { echo "ERROR: missing canonical drift-watchdog unit: $src" >&2; exit 2; }
  install -o root -g root -m 0644 "$src" "/etc/systemd/system/$unit"
done

for unit in "${OBSOLETE_UNITS[@]}"; do
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$unit"
done

step_start system_service_activation
PORT_GUARD="$RELEASE_DIR/tools/release_exporter_port_guard.py"
test -f "$PORT_GUARD" || { echo "ERROR: missing candidate exporter port ownership guard" >&2; exit 9; }
systemctl daemon-reload
# Stop every system-managed exporter BEFORE any restart, then require that
# every port is actually free. Never kill a process selected merely by script
# name (it might belong to a user session or another service).
for unit in "${EXPORTER_UNITS[@]}"; do
  CURRENT_UNIT="$unit"
  timeout --signal=TERM --kill-after=5s 25s systemctl stop "$unit"
done
for unit in "${EXPORTER_UNITS[@]}"; do
  CURRENT_UNIT="$unit"
  /usr/bin/python3 "$PORT_GUARD" --mode free --unit "$unit" --timeout-seconds 12
done
# systemctl active does not prove that a freshly started Python exporter won
# its socket. Require matching listening socket owner and systemd MainPID.
# The privileged host may transiently lose its D-Bus connection while services
# are being activated. Recover only the bounded case where the *approved*
# exporter owns no process AND its socket is genuinely free; never retry an
# unknown/foreign listener, unexpected ownership, or missing MainPID evidence.
ensure_owned_exporter() {
  local unit="$1"
  local check_output
  local attempt
  # A start --no-block may remain queued during host-wide systemd activity.
  # Preserve a hard four-probe bound (4 x 30s), with no acceptance unless the
  # independent socket/MainPID ownership check actually passes.
  for attempt in 1 2 3 4; do
    if check_output="$(/usr/bin/python3 "$PORT_GUARD" --mode owned --unit "$unit" --timeout-seconds 30 2>&1)"; then
      printf '%s\n' "$check_output"
      return 0
    fi
    printf '%s\n' "$check_output" >&2
    # This is the only bounded transient eligible for automatic recovery:
    # no socket owner, and systemd explicitly reported MainPID=0. All other
    # failures go through protected rollback, unchanged.
    if [[ "$check_output" != *"has no listening owner (MainPID=0)"* ]] || [ "$attempt" -eq 4 ]; then
      echo "EXPORTER_OWNERSHIP_RECONCILIATION=FAIL unit=$unit attempt=$attempt" >&2
      return 1
    fi
    /usr/bin/python3 "$PORT_GUARD" --mode free --unit "$unit" --timeout-seconds 4
    # Do not continually restart an in-flight systemd activation job; doing
    # so can prolong a slow but legitimate start until after release rollback.
    # Query the real queue. Failed/unknown queue reads must fail closed.
    local queued_job
    if ! queued_job="$(timeout --signal=TERM --kill-after=5s 15s systemctl show "$unit" --property=Job --value)"; then
      echo "EXPORTER_OWNERSHIP_RECONCILIATION=FAIL unit=$unit reason=job_read_failed" >&2
      return 1
    fi
    if [ -n "$queued_job" ]; then
      echo "EXPORTER_OWNERSHIP_RECONCILIATION=WAIT unit=$unit attempt=$attempt" >&2
    else
      echo "EXPORTER_OWNERSHIP_RECONCILIATION=RETRY unit=$unit attempt=$attempt" >&2
      timeout --signal=TERM --kill-after=5s 15s systemctl restart --no-block "$unit"
    fi
    sleep 3
  done
}
for unit in "${EXPORTER_UNITS[@]}"; do
  CURRENT_UNIT="$unit"
  # Enabling and starting are separate bounded operations. The old
  # systemctl enable --now waited synchronously on a systemd start job and
  # timed out during D-Bus pressure even though the service then started.
  # Queue the job nonblocking and require the independent PID/socket guard
  # to prove the exporter actually owns its listener. No systemctl success
  # response alone can make an exporter count as healthy.
  timeout --signal=TERM --kill-after=5s 15s systemctl enable "$unit"
  timeout --signal=TERM --kill-after=5s 15s systemctl start --no-block "$unit"
  ensure_owned_exporter "$unit"
done
CURRENT_UNIT=""
for timer in "${MAINTENANCE_TIMERS[@]}"; do
  CURRENT_UNIT="$timer"
  systemctl enable --now "$timer"
done
CURRENT_UNIT="$PROVIDER_CANARY_TIMER"
systemctl enable --now "$PROVIDER_CANARY_TIMER"
if [ "$RECOVERY_PROFILE" = "provider_identity_and_authority_recovery" ]; then
  echo "JASON_PROVIDER_CANARY_INITIAL=DEFERRED_UNTIL_IDENTITY_RECOVERY"
else
  CURRENT_UNIT="$PROVIDER_CANARY_SERVICE"
  timeout --signal=TERM --kill-after=5s 45s systemctl start "$PROVIDER_CANARY_SERVICE"
fi

ensure_authority_full_integrity_proof() {
  local evidence=/var/lib/jason/openclaw/operational-full-health.json
  local max_age_seconds=$((30 * 60 * 60))
  local al_uid
  al_uid="$(id -u al)"
  if /usr/bin/python3 - "$evidence" "$max_age_seconds" "$al_uid" <<'PY2'
import json, os, stat, sys, time
path=sys.argv[1]; max_age=int(sys.argv[2]); expected_uid=int(sys.argv[3])
try:
    info=os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise SystemExit(2)
    if info.st_uid != expected_uid:
        raise SystemExit(2)
    age=time.time()-info.st_mtime
    if not 0 <= age <= max_age:
        raise SystemExit(2)
    doc=json.load(open(path, encoding='utf-8'))
    if (doc.get('status') != 'pass' or doc.get('snapshot_source_exit_code') != 0
            or doc.get('provider_contacted') is not False
            or doc.get('provider_credentials_used') is not False
            or doc.get('failures') != []):
        raise SystemExit(2)
except (OSError, ValueError, TypeError, json.JSONDecodeError):
    raise SystemExit(2)
raise SystemExit(0)
PY2
  then
    echo "JASON_AUTHORITY_FULL_INTEGRITY=EXISTING_RECENT_PASS"
    return 0
  fi

  CURRENT_UNIT=jason-openclaw-authority-full-integrity.service
  local state
  state="$(systemctl is-active "$CURRENT_UNIT" 2>/dev/null || true)"
  if [ "$state" = "activating" ] || [ "$state" = "active" ]; then
    echo "JASON_AUTHORITY_FULL_INTEGRITY=WAIT_EXISTING_JOB"
    # `start` on an already-starting oneshot joins the existing start job. It
    # does not restart, stop, cancel or replace the in-flight proof.
    systemctl start "$CURRENT_UNIT"
  else
    systemctl reset-failed "$CURRENT_UNIT" || true
    echo "JASON_AUTHORITY_FULL_INTEGRITY=RUN_REPAIRED_PROOF"
    systemctl start "$CURRENT_UNIT"
  fi
  if [ "$(systemctl show "$CURRENT_UNIT" -p Result --value)" != "success" ]; then
    echo "ERROR: repaired authority full-integrity proof did not complete successfully" >&2
    systemctl status "$CURRENT_UNIT" --no-pager -l || true
    return 1
  fi
  /usr/bin/python3 - "$evidence" "$max_age_seconds" "$al_uid" <<'PY2'
import json, os, stat, sys, time
path=sys.argv[1]; max_age=int(sys.argv[2]); expected_uid=int(sys.argv[3])
info=os.lstat(path)
if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != expected_uid:
    raise SystemExit('authority full-integrity evidence ownership/mode invalid')
if not 0 <= time.time()-info.st_mtime <= max_age:
    raise SystemExit('authority full-integrity evidence stale after proof')
doc=json.load(open(path, encoding='utf-8'))
if (doc.get('status') != 'pass' or doc.get('snapshot_source_exit_code') != 0
        or doc.get('provider_contacted') is not False
        or doc.get('provider_credentials_used') is not False
        or doc.get('failures') != []):
    raise SystemExit('authority full-integrity evidence did not prove PASS')
PY2
  echo "JASON_AUTHORITY_FULL_INTEGRITY=FRESH_PASS"
}

ensure_authority_full_integrity_proof

for unit in "${MAINTENANCE_SERVICES[@]}"; do
  CURRENT_UNIT="$unit"
  if [ "$unit" = "jason-openclaw-authority-health.service" ]; then
    # An in-flight legacy full SQLite scan can leave this oneshot activating.
    # Never block on, cancel, restart or kill that older job. Prove a current
    # fast-health PASS against the exact newly installed systemd unit instead.
    AUTHORITY_HANDOFF="$RELEASE_DIR/tools/release_authority_fast_health_handoff.py"
    test -f "$AUTHORITY_HANDOFF" || {
      echo "ERROR: missing bounded authority fast-health handoff" >&2
      exit 9
    }
    /usr/bin/python3 "$AUTHORITY_HANDOFF" --release-dir "$RELEASE_DIR"
  else
    timeout --signal=TERM --kill-after=5s 120s systemctl start "$unit"
  fi
done
CURRENT_UNIT=""
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
# Legacy full-scan completion can overwrite fast evidence during transition.
# Recheck independent fast-mode evidence before accepting the host service.
CURRENT_UNIT="jason-openclaw-authority-health.service"
/usr/bin/python3 "$AUTHORITY_HANDOFF" --release-dir "$RELEASE_DIR" --verify-only
CURRENT_UNIT=""
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
  engineering_pipeline.py \
  pmv3_engineering_controller.py \
  release_breaker_recovery_manager.py \
  engineering_supervisor.py \
  engineering_evidence_tools.py \
  todo_engineering_intake.py \
  todo_release_bridge.py \
  operational_acceptance_reader.py \
  release_manager_gate.py \
  change_integration_gate.py \
  documentation_impact_gate.py; do
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

# Remove unmanaged legacy user units that are not represented in authoritative production source.
# These are dormant residues superseded by governed production paths and/or
# canonical system services. Their developer/worktree execution sources are
# forbidden in production.
step_start obsolete_user_unit_cleanup
for unit in \
  jason-toner-exporter.service \
  jason-autonomous-repair-runner.service \
  jason-autonomous-repair-runner.path \
  jason-resolution-memory-exporter.service \
  jason-playbook-exporter.service \
  jason-pr-integration-reconciler.service \
  jason-pr-integration-reconciler.timer; do
  run_as_al systemctl --user disable --now "$unit" >/dev/null 2>&1 || true
  rm -f "/home/al/.config/systemd/user/$unit" "/home/al/.config/systemd/user/default.target.wants/$unit"
  run_as_al systemctl --user daemon-reload
  state="$(run_as_al systemctl --user is-active "$unit" 2>/dev/null || true)"
  enabled="$(run_as_al systemctl --user is-enabled "$unit" 2>/dev/null || true)"
  if [ "$state" = "active" ] || [ "$state" = "activating" ] || [ "$enabled" = "enabled" ]; then
    echo "ERROR: unmanaged user unit remains active/enabled: $unit" >&2
    exit 9
  fi
done
run_as_al systemctl --user reset-failed >/dev/null 2>&1 || true
step_pass obsolete_user_unit_cleanup
echo "JASON_OBSOLETE_USER_UNIT_CLEANUP=PASS"

# Retain only the newest bounded set of stopped rollback containers. Current
# rollback capability is image-based; these exited containers are historical
# deployment residue, not rollback authority.
step_start rollback_container_retention
mapfile -t rollback_containers < <(
  docker ps -a --filter status=exited --format '{{.CreatedAt}}|{{.Names}}' \
    | awk -F'|' '$2 ~ /^jason-(runtime-rollback-|mcp-pilot-rollback-|mcp-rollback-|teams-gateway-rollback-)/ {print}' \
    | sort -r \
    | cut -d'|' -f2-
)
ROLLBACK_CONTAINER_RETENTION=20
if [ "${#rollback_containers[@]}" -gt "$ROLLBACK_CONTAINER_RETENTION" ]; then
  for name in "${rollback_containers[@]:$ROLLBACK_CONTAINER_RETENTION}"; do
    docker rm "$name" >/dev/null
  done
fi
remaining_rollback_count="$(( $(docker ps -a --filter status=exited --format '{{.Names}}' | grep -Ec '^jason-(runtime-rollback-|mcp-pilot-rollback-|mcp-rollback-|teams-gateway-rollback-)' || true) ))"
if [ "$remaining_rollback_count" -gt "$ROLLBACK_CONTAINER_RETENTION" ]; then
  echo "ERROR: stopped rollback-container retention remains above policy: $remaining_rollback_count" >&2
  exit 9
fi
step_pass rollback_container_retention
echo "JASON_ROLLBACK_CONTAINER_RETENTION=PASS count=$remaining_rollback_count"

step_pass user_worker_reconciliation
echo "JASON_USER_WORKER_RECONCILIATION=PASS"
echo "ENGINEERING_SOURCE_REPO=$ENGINEERING_SOURCE_REPO"
echo "DOCUMENTATION_SOURCE_REPO=$DOCUMENTATION_SOURCE_REPO"

# Install the exact root host worker and policy rollback helper FIRST, so
# any subsequent protected-policy migration is reversible even if the
# root transition install fails before the release can be certified.
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
# Align the independent root transition processor and its exact reviewed
# root-only policy only AFTER the rollback-capable host worker is installed. A retry
# identity accepted by the Release Manager must also be accepted by the root
# processor; otherwise final closeout unnecessarily rolls production back.
# Install the newly staged user units BEFORE committing them as REQUIRED and
# before the final drift guard. Do not replace the running release controller.
step_start held_approval_user_unit_install
run_as_al /usr/bin/python3 "$RELEASE_DIR/tools/install_release_manager.py" \
  --approval-units-only --activate
step_pass held_approval_user_unit_install

# PM V2 shadow is release-owned and may only be activated when the exact
# candidate desired-state policy declares it. The first protected-core
# bootstrap release intentionally defers this unit so the currently installed
# root helper can accept the release, stage the new reviewed helper, and close
# the bootstrap loop without weakening root policy validation.
PM_V2_SHADOW_UNIT="jason-pm-v2-shadow.service"
PM_V2_SHADOW_DECLARED="$(/usr/bin/python3 - "$RELEASE_DIR/config/production-desired-state.json" "$PM_V2_SHADOW_UNIT" <<'PY2'
import json, sys
from pathlib import Path
policy=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
unit=sys.argv[2]
allowed=set(policy.get("allowed_user_units") or [])
required=set(policy.get("required_user_units") or [])
print("yes" if unit in (allowed | required) else "no")
PY2
)"
if [ "$PM_V2_SHADOW_DECLARED" = "yes" ]; then
  step_start pm_v2_shadow_user_unit_install
  PM_V2_SHADOW_SOURCE="$RELEASE_DIR/infrastructure/openclaw-operations/systemd/user/$PM_V2_SHADOW_UNIT"
  test -f "$PM_V2_SHADOW_SOURCE" || { echo "ERROR: PM V2 shadow unit is missing" >&2; exit 9; }
  install -d -o al -g al -m 0700 /var/lib/jason/pm-v2 /var/lib/jason/openclaw/pm-v2
  install -o al -g al -m 0644 "$PM_V2_SHADOW_SOURCE" "/home/al/.config/systemd/user/$PM_V2_SHADOW_UNIT"
  run_as_al systemctl --user daemon-reload
  run_as_al systemctl --user enable --now "$PM_V2_SHADOW_UNIT"
  if [ "$(run_as_al systemctl --user is-active "$PM_V2_SHADOW_UNIT" 2>/dev/null || true)" != "active" ]; then
    echo "ERROR: PM V2 shadow service is not active after governed install" >&2
    exit 9
  fi
  step_pass pm_v2_shadow_user_unit_install
  echo "JASON_PM_V2_SHADOW_RECONCILIATION=PASS"
else
  echo "JASON_PM_V2_SHADOW_RECONCILIATION=DEFERRED_BOOTSTRAP"
fi

step_start boot_recovery_install
BOOT_RECOVERY_SCRIPT="$RELEASE_DIR/tools/jason_boot_recovery.py"
BOOT_RECOVERY_SERVICE="$RELEASE_DIR/infrastructure/boot-recovery/jason-boot-recovery.service"
BOOT_RECOVERY_TIMER="$RELEASE_DIR/infrastructure/boot-recovery/jason-boot-recovery.timer"
for required in "$BOOT_RECOVERY_SCRIPT" "$BOOT_RECOVERY_SERVICE" "$BOOT_RECOVERY_TIMER"; do
  test -f "$required" || { echo "ERROR: boot recovery source missing: $required" >&2; exit 9; }
done
install -o root -g root -m 0750 "$BOOT_RECOVERY_SCRIPT" /usr/local/sbin/jason-boot-recovery
install -o root -g root -m 0644 "$BOOT_RECOVERY_SERVICE" /etc/systemd/system/jason-boot-recovery.service
install -o root -g root -m 0644 "$BOOT_RECOVERY_TIMER" /etc/systemd/system/jason-boot-recovery.timer
cmp -s "$BOOT_RECOVERY_SCRIPT" /usr/local/sbin/jason-boot-recovery || {
  echo "ERROR: installed boot recovery controller differs from exact immutable release" >&2
  exit 9
}
cmp -s "$BOOT_RECOVERY_SERVICE" /etc/systemd/system/jason-boot-recovery.service || {
  echo "ERROR: installed boot recovery service differs from exact immutable release" >&2
  exit 9
}
cmp -s "$BOOT_RECOVERY_TIMER" /etc/systemd/system/jason-boot-recovery.timer || {
  echo "ERROR: installed boot recovery timer differs from exact immutable release" >&2
  exit 9
}
systemctl daemon-reload
systemctl enable jason-boot-recovery.service jason-boot-recovery.timer >/dev/null
if [ "$(systemctl is-active jason-boot-recovery.timer 2>/dev/null || true)" != "active" ]; then
  systemctl start jason-boot-recovery.timer
fi
if [ "$(systemctl is-active jason-boot-recovery.timer 2>/dev/null || true)" != "active" ]; then
  echo "ERROR: boot recovery timer is not active after governed install" >&2
  exit 9
fi
step_pass boot_recovery_install
echo "JASON_BOOT_RECOVERY_INSTALL=PASS"

step_start root_release_transition_install
/usr/bin/python3 "$RELEASE_DIR/tools/install_release_control_transition.py"
cmp -s "$RELEASE_DIR/tools/release_control_transition_worker.py" /usr/local/lib/jason/release_control_transition_worker.py || {
  echo "ERROR: installed root release-transition worker differs from production source" >&2
  exit 9
}
if [ "$(systemctl is-active jason-release-control-transition.timer 2>/dev/null || true)" != "active" ]; then
  echo "ERROR: root release-transition timer is not active after production install" >&2
  exit 9
fi
step_pass root_release_transition_install
echo "JASON_ROOT_RELEASE_TRANSITION_RECONCILIATION=PASS"

step_start openbao_identity_lifecycle_install
/usr/bin/python3 "$RELEASE_DIR/tools/install_openbao_identity_lifecycle.py"
cmp -s "$RELEASE_DIR/tools/provider_secret_provision.py" /usr/local/lib/jason/provider_secret_provision.py || {
  echo "ERROR: installed provider secret provisioning library differs from production source" >&2
  exit 9
}
cmp -s "$RELEASE_DIR/tools/openbao_identity_lifecycle.py" /usr/local/lib/jason/openbao_identity_lifecycle.py || {
  echo "ERROR: installed OpenBao identity lifecycle library differs from production source" >&2
  exit 9
}
cmp -s "$RELEASE_DIR/tools/openbao_identity_lifecycle_worker.py" /usr/local/lib/jason/openbao_identity_lifecycle_worker.py || {
  echo "ERROR: installed OpenBao identity lifecycle worker differs from production source" >&2
  exit 9
}
if [ "$(systemctl is-active jason-openbao-identity-lifecycle.timer 2>/dev/null || true)" != "active" ]; then
  echo "ERROR: OpenBao identity lifecycle timer is not active after production install" >&2
  exit 9
fi
step_pass openbao_identity_lifecycle_install
echo "JASON_OPENBAO_IDENTITY_LIFECYCLE_RECONCILIATION=PASS"

if [ "$RECOVERY_PROFILE" = "provider_identity_and_authority_recovery" ]; then
  step_start provider_identity_release_recovery
  /usr/bin/python3 /usr/local/lib/jason/openbao_identity_lifecycle.py \
    recover-release --source-revision "$SOURCE_REVISION"

  docker restart jason-runtime jason-mcp-pilot >/dev/null
  RUNTIME_RECOVERED=0
  for attempt in $(seq 1 60); do
    runtime_revision="$(docker inspect jason-runtime --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
    runtime_health="$(docker inspect jason-runtime --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || true)"
    mcp_revision="$(docker inspect jason-mcp-pilot --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
    mcp_state="$(docker inspect jason-mcp-pilot --format '{{.State.Status}}' 2>/dev/null || true)"
    if [ "$runtime_revision" = "$SOURCE_REVISION" ] \
       && [ "$runtime_health" = "healthy" ] \
       && [ "$mcp_revision" = "$SOURCE_REVISION" ] \
       && [ "$mcp_state" = "running" ]; then
      RUNTIME_RECOVERED=1
      break
    fi
    sleep 2
  done
  if [ "$RUNTIME_RECOVERED" -ne 1 ]; then
    echo "ERROR: provider identity recovery did not restore exact candidate runtime/MCP health" >&2
    exit 9
  fi

  CURRENT_UNIT="$PROVIDER_CANARY_SERVICE"
  CANARY_STARTED_AT="$(date +%s)"
  systemctl start "$PROVIDER_CANARY_SERVICE"
  /usr/bin/python3 - "$CANARY_STARTED_AT" <<'PY2'
import json, sys, time
from pathlib import Path
started=float(sys.argv[1])
p=Path('/var/lib/jason/provider-health-canaries.json')
d=json.loads(p.read_text(encoding='utf-8'))
generated=d.get('generated_at_epoch')
if (not isinstance(generated,(int,float)) or generated < started - 1
        or generated > time.time() + 10
        or d.get('policy') != 'provider-health-canary-v1'
        or d.get('principal') != 'jason-provider-canary'):
    raise SystemExit('provider canary evidence is stale or outside reviewed contract')
items=[x for x in d.get('results',[]) if isinstance(x,dict) and x.get('provider')=='autotask']
if not items or any(x.get('healthy') is not True or x.get('error_class') != 'none' for x in items):
    raise SystemExit('Autotask governed provider canary did not prove healthy after identity recovery')
PY2
  CURRENT_UNIT=""

  run_as_al systemctl --user start jason-dnsfilter-boundary-reconcile.service
  if [ "$(run_as_al systemctl --user show jason-dnsfilter-boundary-reconcile.service -p Result --value)" != "success" ]; then
    echo "ERROR: DNSFilter reconciliation did not pass after identity recovery" >&2
    exit 9
  fi

  CCC_REVIEW="/var/lib/jason/ccc/material-review-${SOURCE_REVISION:0:16}.json"
  if [ ! -f "$CCC_REVIEW" ]; then
    echo "ERROR: candidate Teams CCC material review is missing" >&2
    exit 9
  fi
  CCC_STARTED_AT="$(date +%s)"
  /usr/bin/bash "$RELEASE_DIR/tools/install_ccc_scheduler.sh" "$SOURCE_REVISION" "$CCC_REVIEW"
  /usr/bin/python3 - "$SOURCE_REVISION" "$CCC_STARTED_AT" <<'PY2'
import json, sys, time
from pathlib import Path
sha=sys.argv[1]; started=float(sys.argv[2])
p=Path('/var/lib/jason/ccc/latest.json')
d=json.loads(p.read_text(encoding='utf-8'))
finished=str(d.get('finished_at') or '')
try:
    epoch=__import__('datetime').datetime.fromisoformat(finished.replace('Z','+00:00')).timestamp()
except Exception:
    raise SystemExit('CCC latest evidence has invalid finished_at')
if (epoch < started - 1 or epoch > time.time()+10
        or d.get('status') != 'PASS'
        or d.get('source_revision') != sha
        or d.get('runtime_revision') != sha):
    raise SystemExit('CCC did not freshly prove exact candidate/runtime PASS after recovery')
PY2
  echo "JASON_CCC_POST_RECOVERY=PASS"
  step_pass provider_identity_release_recovery
  echo "JASON_PROVIDER_IDENTITY_RELEASE_RECOVERY=PASS"
else
  echo "JASON_PROVIDER_IDENTITY_RELEASE_RECOVERY=NOT_APPLICABLE"
fi

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

# The scheduled Grafana assurance can run while the production reconciler is
# restarting the usage-attribution exporter. A genuine transient missing
# Prometheus series leaves the assurance oneshot in systemd's failed state.
# Re-execute the REAL checker only after exporters are verified and service
# activation has completed; never reset-failed, mask, or ignore its result.
step_start post_exporter_grafana_assurance
if systemctl cat jason-grafana-assurance.service >/dev/null 2>&1; then
  GRAFANA_REVALIDATION_PASS=0
  # The existing usage-attribution scrape interval is 120s. A healthy exporter
  # restart must be followed by a real scrape, not only three 10s pauses.
  # Bound the whole observation window; no check is skipped or forced PASS.
  GRAFANA_REVALIDATION_DEADLINE=$((SECONDS + 150))
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    remaining=$((GRAFANA_REVALIDATION_DEADLINE - SECONDS))
    if [ "$remaining" -le 0 ]; then break; fi
    check_timeout=$((remaining < 20 ? remaining : 20))
    if timeout --signal=TERM --kill-after=5s "${check_timeout}s" \
        systemctl start jason-grafana-assurance.service \
        && [ "$(systemctl show jason-grafana-assurance.service -p Result --value)" = "success" ]; then
      echo "GRAFANA_POST_EXPORTER_ASSURANCE=PASS attempt=$attempt"
      GRAFANA_REVALIDATION_PASS=1
      break
    fi
    remaining=$((GRAFANA_REVALIDATION_DEADLINE - SECONDS))
    if [ "$attempt" -lt 12 ] && [ "$remaining" -gt 0 ]; then
      sleep "$((remaining < 15 ? remaining : 15))"
    fi
  done
  if [ "$GRAFANA_REVALIDATION_PASS" -ne 1 ]; then
    echo "ERROR: real Grafana assurance remains failed after exporter readiness" >&2
    systemctl status jason-grafana-assurance.service --no-pager -l || true
    exit 9
  fi
else
  echo "GRAFANA_POST_EXPORTER_ASSURANCE=NOT_INSTALLED"
fi
step_pass post_exporter_grafana_assurance

# Prove declared production desired-state convergence before host reconciliation
# can report success. This catches unknown active units/containers, forbidden
# developer execution paths, missing required surfaces, and rollback residue.
step_start production_drift_guard
systemctl enable --now "$DRIFT_WATCHDOG_TIMER"
timeout --signal=TERM --kill-after=5s 60s systemctl start "$DRIFT_WATCHDOG_SERVICE" || {
  systemctl status "$DRIFT_WATCHDOG_SERVICE" --no-pager -l || true
  echo "ERROR: production drift watchdog initial convergence check failed" >&2
  exit 9
}
if [ "$(systemctl is-active "$DRIFT_WATCHDOG_TIMER" 2>/dev/null || true)" != "active" ]; then
  echo "ERROR: production drift watchdog timer is not active" >&2
  exit 9
fi
DRIFT_EVIDENCE="/var/lib/jason/openclaw/release-manager/production-drift.json"
if ! /usr/bin/python3 "$RELEASE_DIR/tools/production_drift_guard.py" \
  --config "$RELEASE_DIR/config/production-desired-state.json" \
  --output "$DRIFT_EVIDENCE"; then
  cat "$DRIFT_EVIDENCE" >&2 || true
  echo "ERROR: production desired-state drift remains after reconciliation" >&2
  exit 9
fi
step_pass production_drift_guard
echo "JASON_PRODUCTION_DRIFT_GUARD=PASS evidence=$DRIFT_EVIDENCE"

# Documentation/control-board publication is deliberately outside the privileged
# host-alignment transaction. Release Manager performs it after runtime, MCP,
# immutable host, workers, and observability have aligned to the exact SHA.
echo "POST_SUCCESS_DOCUMENTATION_RECONCILIATION=DEFERRED_TO_RELEASE_MANAGER"
