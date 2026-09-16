#!/usr/bin/env bash
set -uo pipefail

# Rollback-protected deployment for Jason production-health observability only.
# It must not restart/recreate Jason runtime, Jason MCP, OpenBao, Ollama,
# node-exporter, or any provider-facing service.

REPO_ROOT="${JASON_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
SHOWCASE_DIR="$REPO_ROOT/infrastructure/showcase"
NEW_COMPOSE="$SHOWCASE_DIR/compose.yaml"
UNIT="jason-production-health-exporter.service"
UNIT_SRC="$SHOWCASE_DIR/systemd/$UNIT"
BACKUP_DIR="${JASON_PRODUCTION_HEALTH_DEPLOY_BACKUP_DIR:-/tmp/jason-production-health-rollback-$(date -u +%Y%m%dT%H%M%SZ)}"
MUTATED=0
RECOVERED_ENV=""

say() { printf '%s\n' "$*"; }
container_id_or_empty() { docker inspect -f '{{.Id}}' "$1" 2>/dev/null || true; }
container_running() { [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" == "true" ]]; }

cleanup() {
  if [[ -n "${RECOVERED_ENV:-}" ]]; then
    rm -f "$RECOVERED_ENV"
  fi
}
trap cleanup EXIT

require_file() {
  [[ -f "$1" ]] || { say "PRECHECK=FAIL missing file: $1"; return 1; }
}

wait_http() {
  local url="$1" tries="${2:-30}" delay="${3:-1}" attempt
  for attempt in $(seq 1 "$tries"); do
    curl -fsS "$url" >/dev/null 2>&1 && return 0
    sleep "$delay"
  done
  return 1
}

recover_compose_env_from_running_grafana() {
  local env_dump password_count
  RECOVERED_ENV="$(mktemp)" || return 1
  chmod 600 "$RECOVERED_ENV" || return 1
  env_dump="$(docker inspect jason-grafana --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null)" || return 1

  {
    printf '%s\n' "$env_dump" | awk '
      index($0,"GF_SECURITY_ADMIN_USER=")==1 {
        print "GRAFANA_ADMIN_USER=" substr($0,length("GF_SECURITY_ADMIN_USER=")+1)
      }
      index($0,"GF_SECURITY_ADMIN_PASSWORD=")==1 {
        print "GRAFANA_ADMIN_PASSWORD=" substr($0,length("GF_SECURITY_ADMIN_PASSWORD=")+1)
      }
    '
  } > "$RECOVERED_ENV" || return 1

  if ! grep -q '^GRAFANA_ADMIN_USER=' "$RECOVERED_ENV"; then
    printf 'GRAFANA_ADMIN_USER=admin\n' >> "$RECOVERED_ENV"
  fi
  password_count="$(grep -c '^GRAFANA_ADMIN_PASSWORD=.' "$RECOVERED_ENV" || true)"
  [[ "$password_count" -eq 1 ]] || return 1

  OLD_ENV="$RECOVERED_ENV"
  say "SHOWCASE_ENV_SOURCE=RECOVERED_FROM_RUNNING_GRAFANA"
  say "SHOWCASE_ENV_VALUES_PRINTED=NO"
}

install_unit_from_source() {
  local temporary
  temporary="$(mktemp)" || return 1
  python3 - "$UNIT_SRC" "$temporary" "$REPO_ROOT" <<'PY'
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
  if [[ $rc -ne 0 ]]; then rm -f "$temporary"; return $rc; fi
  sudo install -m 0644 "$temporary" "/etc/systemd/system/$UNIT" || {
    rm -f "$temporary"
    return 1
  }
  rm -f "$temporary"
}

record_unit_state() {
  if sudo test -f "/etc/systemd/system/$UNIT"; then
    sudo cp -a "/etc/systemd/system/$UNIT" "$BACKUP_DIR/$UNIT" || return 1
    printf 'present\n' > "$BACKUP_DIR/unit.present"
  else
    printf 'absent\n' > "$BACKUP_DIR/unit.present"
  fi
  systemctl is-enabled "$UNIT" 2>/dev/null > "$BACKUP_DIR/unit.enabled" || true
  systemctl is-active "$UNIT" 2>/dev/null > "$BACKUP_DIR/unit.active" || true
}

restore_unit() {
  local present enabled active
  present="$(cat "$BACKUP_DIR/unit.present" 2>/dev/null || true)"
  enabled="$(cat "$BACKUP_DIR/unit.enabled" 2>/dev/null || true)"
  active="$(cat "$BACKUP_DIR/unit.active" 2>/dev/null || true)"

  if [[ "$present" == "present" ]]; then
    sudo install -m 0644 "$BACKUP_DIR/$UNIT" "/etc/systemd/system/$UNIT" || true
  else
    sudo systemctl disable --now "$UNIT" >/dev/null 2>&1 || true
    sudo rm -f "/etc/systemd/system/$UNIT"
  fi
  sudo systemctl daemon-reload || true

  if [[ "$present" == "present" ]]; then
    [[ "$enabled" == "enabled" ]] && sudo systemctl enable "$UNIT" >/dev/null 2>&1 || sudo systemctl disable "$UNIT" >/dev/null 2>&1 || true
    [[ "$active" == "active" ]] && sudo systemctl restart "$UNIT" >/dev/null 2>&1 || sudo systemctl stop "$UNIT" >/dev/null 2>&1 || true
  fi
}

rollback() {
  say "ROLLBACK=START"
  restore_unit
  if [[ -n "${OLD_PROJECT:-}" && -f "${OLD_COMPOSE:-}" && -f "${OLD_ENV:-}" ]]; then
    docker compose -p "$OLD_PROJECT" --env-file "$OLD_ENV" -f "$OLD_COMPOSE" \
      up -d --no-deps prometheus grafana >/dev/null 2>&1 || true
  fi
  say "ROLLBACK=COMPLETE"
  say "BACKUP_DIR=$BACKUP_DIR"
}

precheck() {
  say "========== PRODUCTION HEALTH DASHBOARD PRECHECK =========="
  [[ -n "$REPO_ROOT" && ( -d "$REPO_ROOT/.git" || -f "$REPO_ROOT/.git" ) ]] || {
    say "PRECHECK=FAIL invalid repository root: $REPO_ROOT"; return 1;
  }

  for path in \
    "$NEW_COMPOSE" \
    "$SHOWCASE_DIR/production_health_exporter.py" \
    "$SHOWCASE_DIR/tests/test_production_health_exporter.py" \
    "$SHOWCASE_DIR/grafana/dashboards/jason-production-health.json" \
    "$SHOWCASE_DIR/prometheus/prometheus.yml" \
    "$SHOWCASE_DIR/prometheus/alerts/jason-production.yml" \
    "$SHOWCASE_DIR/prometheus/file_sd/jason-production-health.json" \
    "$UNIT_SRC"; do
    require_file "$path" || return 1
  done

  [[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]] || { say "PRECHECK=FAIL deployment worktree is dirty"; return 1; }
  command -v docker >/dev/null || { say "PRECHECK=FAIL docker unavailable"; return 1; }
  docker compose version >/dev/null 2>&1 || { say "PRECHECK=FAIL docker compose unavailable"; return 1; }
  command -v curl >/dev/null || { say "PRECHECK=FAIL curl unavailable"; return 1; }
  command -v python3 >/dev/null || { say "PRECHECK=FAIL python3 unavailable"; return 1; }
  sudo -v || { say "PRECHECK=FAIL sudo unavailable"; return 1; }

  for name in jason-runtime jason-mcp-pilot openbao jason-prometheus jason-grafana; do
    container_running "$name" || { say "PRECHECK=FAIL $name not running"; return 1; }
  done

  OLD_PROJECT="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' jason-grafana 2>/dev/null || true)"
  OLD_SHOWCASE="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' jason-grafana 2>/dev/null || true)"
  OLD_COMPOSE="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' jason-grafana 2>/dev/null || true)"
  PROM_PROJECT="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' jason-prometheus 2>/dev/null || true)"
  [[ -n "$OLD_PROJECT" && "$OLD_PROJECT" == "$PROM_PROJECT" ]] || { say "PRECHECK=FAIL Grafana/Prometheus compose project mismatch"; return 1; }
  [[ -n "$OLD_SHOWCASE" && -d "$OLD_SHOWCASE" ]] || { say "PRECHECK=FAIL existing showcase working directory unavailable"; return 1; }
  [[ "$OLD_COMPOSE" != *,* && -f "$OLD_COMPOSE" ]] || { say "PRECHECK=FAIL existing compose file unavailable or ambiguous"; return 1; }

  OLD_ENV="$OLD_SHOWCASE/.env"
  if [[ -f "$OLD_ENV" ]]; then
    say "SHOWCASE_ENV_SOURCE=EXISTING_MODE_600_FILE"
  else
    recover_compose_env_from_running_grafana || {
      say "PRECHECK=FAIL existing showcase .env unavailable and safe recovery failed"
      return 1
    }
  fi

  mkdir -p "$BACKUP_DIR" || return 1
  chmod 700 "$BACKUP_DIR" || return 1
  record_unit_state || return 1

  RUNTIME_BEFORE="$(container_id_or_empty jason-runtime)"
  MCP_BEFORE="$(container_id_or_empty jason-mcp-pilot)"
  OPENBAO_BEFORE="$(container_id_or_empty openbao)"
  OLLAMA_BEFORE="$(container_id_or_empty jason-ollama)"
  NODE_BEFORE="$(container_id_or_empty jason-node-exporter)"

  say "SOURCE_HEAD=$(git -C "$REPO_ROOT" rev-parse HEAD)"
  say "EXISTING_COMPOSE_PROJECT=$OLD_PROJECT"
  say "EXISTING_SHOWCASE=$OLD_SHOWCASE"
  say "BACKUP_DIR=$BACKUP_DIR"
  say "PRECHECK=PASS"
}

deploy() {
  say "========== SOURCE VALIDATION =========="
  python3 -m py_compile "$SHOWCASE_DIR/production_health_exporter.py" || return 1
  python3 -m json.tool "$SHOWCASE_DIR/grafana/dashboards/jason-production-health.json" >/dev/null || return 1
  docker run --rm --entrypoint /bin/promtool \
    -v "$SHOWCASE_DIR/prometheus:/etc/prometheus:ro" \
    prom/prometheus:v3.7.3 \
    check config /etc/prometheus/prometheus.yml || return 1
  say "SOURCE_VALIDATION=PASS"

  say "========== INSTALL SECRET-SAFE PRODUCTION HEALTH EXPORTER =========="
  install_unit_from_source || return 1
  MUTATED=1
  sudo systemctl daemon-reload || return 1
  sudo systemctl enable "$UNIT" >/dev/null || return 1
  sudo systemctl restart "$UNIT" || return 1
  wait_http "http://127.0.0.1:9467/metrics" 30 1 || return 1
  curl -fsS http://127.0.0.1:9467/metrics | grep -q '^jason_production_health_exporter_build_info' || return 1
  say "PRODUCTION_HEALTH_EXPORTER=PASS"

  say "========== REFRESH PROMETHEUS / GRAFANA ONLY =========="
  docker compose -p "$OLD_PROJECT" --env-file "$OLD_ENV" -f "$NEW_COMPOSE" \
    up -d --no-deps prometheus grafana || return 1
  wait_http "http://127.0.0.1:9090/-/healthy" 45 1 || return 1
  wait_http "http://127.0.0.1:3000/api/health" 45 1 || return 1
  say "MONITORING_CONTAINERS=PASS"

  [[ "$(container_id_or_empty jason-runtime)" == "$RUNTIME_BEFORE" ]] || { say "ISOLATION=FAIL jason-runtime changed"; return 1; }
  [[ "$(container_id_or_empty jason-mcp-pilot)" == "$MCP_BEFORE" ]] || { say "ISOLATION=FAIL jason-mcp-pilot changed"; return 1; }
  [[ "$(container_id_or_empty openbao)" == "$OPENBAO_BEFORE" ]] || { say "ISOLATION=FAIL openbao changed"; return 1; }
  [[ "$(container_id_or_empty jason-ollama)" == "$OLLAMA_BEFORE" ]] || { say "ISOLATION=FAIL jason-ollama changed"; return 1; }
  [[ "$(container_id_or_empty jason-node-exporter)" == "$NODE_BEFORE" ]] || { say "ISOLATION=FAIL jason-node-exporter changed"; return 1; }
  say "CORE_ISOLATION=PASS"

  say "========== PROMETHEUS TARGET / RULE ACCEPTANCE =========="
  python3 - <<'PY'
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen
query = urlencode({"query": 'up{job="jason-production-health"}'})
deadline = time.monotonic() + 75
while time.monotonic() < deadline:
    try:
        with urlopen(f"http://127.0.0.1:9090/api/v1/query?{query}", timeout=5) as response:
            rows = json.load(response).get("data", {}).get("result", [])
        if any(str(row.get("value", [None, "0"])[1]) == "1" for row in rows):
            print("PROMETHEUS_PRODUCTION_HEALTH=UP")
            break
    except Exception:
        pass
    time.sleep(3)
else:
    raise SystemExit("production-health Prometheus target did not become UP")

with urlopen("http://127.0.0.1:9090/api/v1/rules?type=alert", timeout=5) as response:
    groups = json.load(response).get("data", {}).get("groups", [])
names = {rule.get("name") for group in groups for rule in group.get("rules", []) if isinstance(rule, dict)}
required = {"JasonRuntimeNotHealthy", "JasonMCPNotRunning", "JasonOpenBaoNotReady", "JasonKernelErrorsDetected", "JasonMCPDuplicateEnvironment"}
missing = sorted(required - names)
if missing:
    raise SystemExit("required production alert rules missing: " + ", ".join(missing))
print("PROMETHEUS_PRODUCTION_RULES=PASS")
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
    if raw and not raw.lstrip().startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
user = values.get("GRAFANA_ADMIN_USER", "admin")
password = values.get("GRAFANA_ADMIN_PASSWORD", "")
if not password:
    raise SystemExit("Grafana credential unavailable in deployment environment")
auth = base64.b64encode(f"{user}:{password}".encode()).decode()
request = Request("http://127.0.0.1:3000/api/dashboards/uid/jason-production-health", headers={"Authorization": f"Basic {auth}"})
with urlopen(request, timeout=5) as response:
    payload = json.load(response)
if payload.get("dashboard", {}).get("uid") != "jason-production-health":
    raise SystemExit("Jason Production Health dashboard was not provisioned")
print("GRAFANA_PRODUCTION_HEALTH_DASHBOARD=PASS")
PY
  [[ $? -eq 0 ]] || return 1

  say "========== LIVE METRIC CONTRACT =========="
  METRICS="$(curl -fsS http://127.0.0.1:9467/metrics)" || return 1
  for metric in jason_production_component_health jason_mcp_contract jason_mcp_env_duplicate_count jason_mcp_required_secret_mount_contract jason_host_kernel_error_count jason_root_filesystem_writable jason_mcp_rollback_available; do
    printf '%s\n' "$METRICS" | grep -q "^${metric}" || { say "METRIC_CONTRACT=FAIL missing $metric"; return 1; }
  done
  say "METRIC_CONTRACT=PASS"

  say "========== DEPLOYMENT PASS =========="
  say "RUNTIME_CHANGED=NO"
  say "MCP_CHANGED=NO"
  say "OPENBAO_CHANGED=NO"
  say "PROVIDER_ACCESS=NO"
  say "PROVIDER_WRITES=NO"
  say "PRODUCTION_HEALTH_EXPORTER=http://127.0.0.1:9467/metrics"
  say "GRAFANA_DASHBOARD_UID=jason-production-health"
  say "BACKUP_DIR=$BACKUP_DIR"
  return 0
}

if ! precheck; then
  say "DEPLOYMENT=NOT_STARTED"
  exit 1
fi
if deploy; then
  exit 0
fi
say "DEPLOYMENT=FAIL"
[[ "$MUTATED" -eq 1 ]] && rollback
exit 1
