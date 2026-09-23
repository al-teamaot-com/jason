#!/usr/bin/env bash
set -uo pipefail

# Minimal, rollback-protected deployment for Jason usage telemetry dashboards.
# This intentionally does NOT restart Jason runtime, Jason MCP, Ollama, node-exporter,
# Caddy, or any provider-facing service. It updates only the two usage exporters and
# the existing Prometheus/Grafana showcase containers.

REPO_ROOT="${JASON_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
SHOWCASE_DIR="$REPO_ROOT/infrastructure/showcase"
NEW_COMPOSE="$SHOWCASE_DIR/compose.yaml"
BACKUP_DIR="${JASON_USAGE_DEPLOY_BACKUP_DIR:-/tmp/jason-usage-dashboard-rollback-$(date -u +%Y%m%dT%H%M%SZ)}"
MUTATED=0

usage_unit="jason-usage-exporter.service"
attribution_unit="jason-usage-attribution-exporter.service"
units=("$usage_unit" "$attribution_unit")

say() {
  printf '%s\n' "$*"
}

require_file() {
  [[ -f "$1" ]] || {
    say "PRECHECK=FAIL missing file: $1"
    return 1
  }
}

container_id_or_empty() {
  docker inspect -f '{{.Id}}' "$1" 2>/dev/null || true
}

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" == "true" ]]
}

wait_http() {
  local url="$1"
  local tries="${2:-30}"
  local delay="${3:-1}"
  local attempt
  for attempt in $(seq 1 "$tries"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

record_unit_state() {
  local unit="$1"
  local key="${unit%.service}"
  if sudo test -f "/etc/systemd/system/$unit"; then
    sudo cp -a "/etc/systemd/system/$unit" "$BACKUP_DIR/$unit"
    printf 'present\n' > "$BACKUP_DIR/$key.present"
  else
    printf 'absent\n' > "$BACKUP_DIR/$key.present"
  fi
  systemctl is-enabled "$unit" 2>/dev/null > "$BACKUP_DIR/$key.enabled" || true
  systemctl is-active "$unit" 2>/dev/null > "$BACKUP_DIR/$key.active" || true
}

install_unit_from_source() {
  local source="$1"
  local unit="$2"
  local temporary
  temporary="$(mktemp)" || return 1
  python3 - "$source" "$temporary" "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1])
destination = Path(sys.argv[2])
repo_root = sys.argv[3]
text = source.read_text(encoding="utf-8")
text = text.replace("/home/al/projects/jason", repo_root)
destination.write_text(text, encoding="utf-8")
PY
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    rm -f "$temporary"
    return $rc
  fi
  sudo install -m 0644 "$temporary" "/etc/systemd/system/$unit" || {
    rm -f "$temporary"
    return 1
  }
  rm -f "$temporary"
}

restore_unit() {
  local unit="$1"
  local key="${unit%.service}"
  local present=""
  present="$(cat "$BACKUP_DIR/$key.present" 2>/dev/null || true)"

  if [[ "$present" == "present" ]]; then
    sudo install -m 0644 "$BACKUP_DIR/$unit" "/etc/systemd/system/$unit" || true
  else
    sudo systemctl disable --now "$unit" >/dev/null 2>&1 || true
    sudo rm -f "/etc/systemd/system/$unit"
  fi
}

rollback() {
  say "ROLLBACK=START"

  for unit in "${units[@]}"; do
    restore_unit "$unit"
  done
  sudo systemctl daemon-reload || true

  for unit in "${units[@]}"; do
    local key="${unit%.service}"
    local present enabled active
    present="$(cat "$BACKUP_DIR/$key.present" 2>/dev/null || true)"
    enabled="$(cat "$BACKUP_DIR/$key.enabled" 2>/dev/null || true)"
    active="$(cat "$BACKUP_DIR/$key.active" 2>/dev/null || true)"
    if [[ "$present" == "present" ]]; then
      if [[ "$enabled" == "enabled" ]]; then
        sudo systemctl enable "$unit" >/dev/null 2>&1 || true
      else
        sudo systemctl disable "$unit" >/dev/null 2>&1 || true
      fi
      if [[ "$active" == "active" ]]; then
        sudo systemctl restart "$unit" >/dev/null 2>&1 || true
      else
        sudo systemctl stop "$unit" >/dev/null 2>&1 || true
      fi
    fi
  done

  if [[ -n "${OLD_PROJECT:-}" && -f "${OLD_COMPOSE:-}" && -f "${OLD_ENV:-}" ]]; then
    docker compose \
      -p "$OLD_PROJECT" \
      --env-file "$OLD_ENV" \
      -f "$OLD_COMPOSE" \
      up -d --no-deps prometheus grafana >/dev/null 2>&1 || true
  fi

  say "ROLLBACK=COMPLETE"
  say "BACKUP_DIR=$BACKUP_DIR"
}

precheck() {
  say "========== USAGE DASHBOARD DEPLOYMENT PRECHECK =========="

  [[ -n "$REPO_ROOT" && -d "$REPO_ROOT/.git" || -f "$REPO_ROOT/.git" ]] || {
    say "PRECHECK=FAIL invalid repository root: $REPO_ROOT"
    return 1
  }

  require_file "$NEW_COMPOSE" || return 1
  require_file "$SHOWCASE_DIR/usage_exporter.py" || return 1
  require_file "$SHOWCASE_DIR/usage_attribution_exporter.py" || return 1
  require_file "$SHOWCASE_DIR/usage_attribution_exporter_runtime.py" || return 1
  require_file "$SHOWCASE_DIR/grafana/dashboards/jason-command-center.json" || return 1
  require_file "$SHOWCASE_DIR/grafana/dashboards/jason-usage-attribution.json" || return 1
  require_file "$SHOWCASE_DIR/prometheus/prometheus.yml" || return 1
  require_file "$SHOWCASE_DIR/systemd/$usage_unit" || return 1
  require_file "$SHOWCASE_DIR/systemd/$attribution_unit" || return 1

  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    say "PRECHECK=FAIL deployment worktree is dirty"
    return 1
  fi

  command -v docker >/dev/null || { say "PRECHECK=FAIL docker unavailable"; return 1; }
  docker compose version >/dev/null 2>&1 || { say "PRECHECK=FAIL docker compose unavailable"; return 1; }
  command -v curl >/dev/null || { say "PRECHECK=FAIL curl unavailable"; return 1; }
  command -v python3 >/dev/null || { say "PRECHECK=FAIL python3 unavailable"; return 1; }
  sudo -v || { say "PRECHECK=FAIL sudo unavailable"; return 1; }

  container_running jason-prometheus || { say "PRECHECK=FAIL jason-prometheus not running"; return 1; }
  container_running jason-grafana || { say "PRECHECK=FAIL jason-grafana not running"; return 1; }

  OLD_PROJECT="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' jason-grafana 2>/dev/null || true)"
  OLD_SHOWCASE="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' jason-grafana 2>/dev/null || true)"
  OLD_COMPOSE="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' jason-grafana 2>/dev/null || true)"
  local prometheus_project
  prometheus_project="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' jason-prometheus 2>/dev/null || true)"

  [[ -n "$OLD_PROJECT" && "$OLD_PROJECT" == "$prometheus_project" ]] || {
    say "PRECHECK=FAIL Grafana/Prometheus compose project mismatch"
    return 1
  }
  [[ -n "$OLD_SHOWCASE" && -d "$OLD_SHOWCASE" ]] || {
    say "PRECHECK=FAIL existing showcase working directory unavailable"
    return 1
  }
  [[ "$OLD_COMPOSE" != *,* && -f "$OLD_COMPOSE" ]] || {
    say "PRECHECK=FAIL existing compose file unavailable or ambiguous"
    return 1
  }
  OLD_ENV="$OLD_SHOWCASE/.env"
  [[ -f "$OLD_ENV" ]] || {
    say "PRECHECK=FAIL existing showcase .env unavailable"
    return 1
  }

  mkdir -p "$BACKUP_DIR" || return 1
  chmod 700 "$BACKUP_DIR" || return 1

  RUNTIME_BEFORE="$(container_id_or_empty jason-runtime)"
  MCP_BEFORE="$(container_id_or_empty jason-mcp-pilot)"
  OLLAMA_BEFORE="$(container_id_or_empty jason-ollama)"
  NODE_BEFORE="$(container_id_or_empty jason-node-exporter)"

  printf '%s\n' "$OLD_PROJECT" > "$BACKUP_DIR/compose-project"
  printf '%s\n' "$OLD_SHOWCASE" > "$BACKUP_DIR/old-showcase"
  printf '%s\n' "$OLD_COMPOSE" > "$BACKUP_DIR/old-compose"

  for unit in "${units[@]}"; do
    record_unit_state "$unit" || return 1
  done

  say "SOURCE_HEAD=$(git -C "$REPO_ROOT" rev-parse HEAD)"
  say "EXISTING_COMPOSE_PROJECT=$OLD_PROJECT"
  say "EXISTING_SHOWCASE=$OLD_SHOWCASE"
  say "BACKUP_DIR=$BACKUP_DIR"
  say "PRECHECK=PASS"
}

deploy() {
  say "========== INSTALL READ-ONLY USAGE EXPORTERS =========="
  install_unit_from_source "$SHOWCASE_DIR/systemd/$usage_unit" "$usage_unit" || return 1
  install_unit_from_source "$SHOWCASE_DIR/systemd/$attribution_unit" "$attribution_unit" || return 1
  MUTATED=1

  sudo systemctl daemon-reload || return 1
  sudo systemctl enable --now "$usage_unit" || return 1
  sudo systemctl enable --now "$attribution_unit" || return 1

  wait_http "http://127.0.0.1:9465/metrics" 30 1 || return 1
  wait_http "http://127.0.0.1:9466/metrics" 30 1 || return 1

  curl -fsS http://127.0.0.1:9465/metrics | grep -q '^jason_usage_exporter_build_info' || return 1
  curl -fsS http://127.0.0.1:9466/metrics | grep -q '^jason_usage_attribution_exporter_build_info' || return 1

  say "EXPORTERS=PASS"

  say "========== REBIND PROMETHEUS/GRAFANA TO VERSIONED DASHBOARD SOURCE =========="
  docker compose \
    -p "$OLD_PROJECT" \
    --env-file "$OLD_ENV" \
    -f "$NEW_COMPOSE" \
    up -d --no-deps prometheus grafana || return 1

  wait_http "http://127.0.0.1:9090/-/healthy" 45 1 || return 1
  wait_http "http://127.0.0.1:3000/api/health" 45 1 || return 1

  say "MONITORING_CONTAINERS=PASS"

  # Ensure this deployment did not touch runtime, MCP, Ollama, or node-exporter.
  [[ "$(container_id_or_empty jason-runtime)" == "$RUNTIME_BEFORE" ]] || {
    say "ISOLATION=FAIL jason-runtime changed"
    return 1
  }
  [[ "$(container_id_or_empty jason-mcp-pilot)" == "$MCP_BEFORE" ]] || {
    say "ISOLATION=FAIL jason-mcp-pilot changed"
    return 1
  }
  [[ "$(container_id_or_empty jason-ollama)" == "$OLLAMA_BEFORE" ]] || {
    say "ISOLATION=FAIL jason-ollama changed"
    return 1
  }
  [[ "$(container_id_or_empty jason-node-exporter)" == "$NODE_BEFORE" ]] || {
    say "ISOLATION=FAIL jason-node-exporter changed"
    return 1
  }
  say "ISOLATION=PASS"

  say "========== PROMETHEUS TARGET ACCEPTANCE =========="
  python3 - <<'PY'
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen

jobs = ("jason-usage", "jason-usage-attribution")
pending = set(jobs)
deadline = time.monotonic() + 75

while pending and time.monotonic() < deadline:
    for job in tuple(pending):
        query = urlencode({"query": f'up{{job="{job}"}}'})
        try:
            with urlopen(
                f"http://127.0.0.1:9090/api/v1/query?{query}",
                timeout=5,
            ) as response:
                payload = json.load(response)
        except Exception:
            continue

        rows = payload.get("data", {}).get("result", [])
        if any(str(row.get("value", [None, "0"])[1]) == "1" for row in rows):
            print(f"PROMETHEUS_{job.upper().replace('-', '_')}=UP")
            pending.remove(job)

    if pending:
        time.sleep(3)

if pending:
    try:
        with urlopen(
            "http://127.0.0.1:9090/api/v1/targets?state=active",
            timeout=5,
        ) as response:
            targets = json.load(response).get("data", {}).get("activeTargets", [])
    except Exception as exc:
        print(f"PROMETHEUS_TARGET_DIAGNOSTIC_ERROR={type(exc).__name__}")
        targets = []

    for target in targets:
        labels = target.get("labels", {})
        job = labels.get("job")
        if job not in pending:
            continue
        print(
            "PROMETHEUS_TARGET_DIAGNOSTIC"
            f" job={job}"
            f" health={target.get('health', '')}"
            f" scrape_url={target.get('scrapeUrl', '')}"
            f" last_error={target.get('lastError', '')!r}"
        )

    raise SystemExit(
        "Prometheus targets not UP after 75 seconds: "
        + ", ".join(sorted(pending))
    )
PY
  [[ $? -eq 0 ]] || return 1

  say "========== GRAFANA PROVISIONING ACCEPTANCE =========="
  python3 - "$OLD_ENV" <<'PY'
import base64
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not raw or raw.lstrip().startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    values[key.strip()] = value.strip()
user = values.get("GRAFANA_ADMIN_USER", "admin")
password = values.get("GRAFANA_ADMIN_PASSWORD", "")
if not password:
    raise SystemExit("Grafana credential unavailable in existing .env")
auth = base64.b64encode(f"{user}:{password}".encode()).decode()
for uid in ("jason-command-center", "jason-usage-attribution"):
    request = Request(
        f"http://127.0.0.1:3000/api/dashboards/uid/{uid}",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urlopen(request, timeout=5) as response:
        payload = json.load(response)
    if payload.get("dashboard", {}).get("uid") != uid:
        raise SystemExit(f"Grafana dashboard not provisioned: {uid}")
    print(f"GRAFANA_{uid.upper().replace('-', '_')}=READY")
PY
  [[ $? -eq 0 ]] || return 1

  say "========== SECRET-SAFE METRIC SURFACE CHECK =========="
  local metric_snapshot
  metric_snapshot="$(mktemp)" || return 1
  curl -fsS http://127.0.0.1:9466/metrics > "$metric_snapshot" || {
    rm -f "$metric_snapshot"
    return 1
  }
  if grep -Eiq '(access_token=|refresh_token=|api_key=|authorization=|bearer[[:space:]])' "$metric_snapshot"; then
    rm -f "$metric_snapshot"
    say "SECRET_SURFACE=FAIL"
    return 1
  fi
  rm -f "$metric_snapshot"
  say "SECRET_SURFACE=PASS"

  say "DASHBOARD_TELEMETRY_DEPLOYMENT=PASS"
  say "BACKUP_DIR=$BACKUP_DIR"
  say "GRAFANA_URL=http://$(hostname -I | awk '{print $1}'):3000"
}

main() {
  precheck || return 1
  if deploy; then
    return 0
  fi
  say "DASHBOARD_TELEMETRY_DEPLOYMENT=FAIL"
  if [[ "$MUTATED" -eq 1 ]]; then
    rollback
  fi
  return 1
}

main
