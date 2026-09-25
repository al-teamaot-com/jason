#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${JASON_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
SHOWCASE_DIR="$REPO_ROOT/infrastructure/showcase"
COMPOSE="$SHOWCASE_DIR/compose.yaml"

say() { printf '%s\n' "$*"; }
container_id() { docker inspect -f '{{.Id}}' "$1" 2>/dev/null || true; }
wait_http() { local url="$1"; for _ in $(seq 1 45); do curl -fsS "$url" >/dev/null 2>&1 && return 0; sleep 1; done; return 1; }

[[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]] || { say "PRECHECK=FAIL dirty repository"; exit 1; }
for f in \
  "$SHOWCASE_DIR/autonomy_flight_recorder_exporter.py" \
  "$SHOWCASE_DIR/grafana/dashboards/jason-autonomy-flight-recorder.json" \
  "$SHOWCASE_DIR/grafana/provisioning/datasources/autonomy-flight-recorder.yaml" \
  "$SHOWCASE_DIR/prometheus/file_sd/jason-autonomy-flight-recorder.json" \
  "$COMPOSE"; do
  [[ -f "$f" ]] || { say "PRECHECK=FAIL missing $f"; exit 1; }
done
python3 -m py_compile "$SHOWCASE_DIR/autonomy_flight_recorder_exporter.py"
python3 -m json.tool "$SHOWCASE_DIR/grafana/dashboards/jason-autonomy-flight-recorder.json" >/dev/null

RUNTIME_BEFORE="$(container_id jason-runtime)"
MCP_BEFORE="$(container_id jason-mcp-pilot)"
OPENBAO_BEFORE="$(container_id openbao)"

OLD_PROJECT="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' jason-grafana)"
OLD_ENV="$SHOWCASE_DIR/.env"
TEMP_ENV=""
if [[ ! -f "$OLD_ENV" ]]; then
  TEMP_ENV="$(mktemp)"
  chmod 600 "$TEMP_ENV"
  docker inspect jason-grafana --format '{{range .Config.Env}}{{println .}}{{end}}' | awk '
    index($0,"GF_SECURITY_ADMIN_USER=")==1 {print "GRAFANA_ADMIN_USER=" substr($0,length("GF_SECURITY_ADMIN_USER=")+1)}
    index($0,"GF_SECURITY_ADMIN_PASSWORD=")==1 {print "GRAFANA_ADMIN_PASSWORD=" substr($0,length("GF_SECURITY_ADMIN_PASSWORD=")+1)}
  ' > "$TEMP_ENV"
  OLD_ENV="$TEMP_ENV"
fi
trap '[[ -n "${TEMP_ENV:-}" ]] && rm -f "$TEMP_ENV"' EXIT

say "========== DEPLOY FLIGHT RECORDER / PROMETHEUS / GRAFANA =========="
docker compose -p "$OLD_PROJECT" --env-file "$OLD_ENV" -f "$COMPOSE" up -d --no-deps autonomy-flight-recorder prometheus grafana >/dev/null
wait_http http://127.0.0.1:9475/healthz
wait_http http://127.0.0.1:9090/-/healthy
wait_http http://127.0.0.1:3000/api/health
curl -fsS http://127.0.0.1:9475/metrics | grep -q '^jason_autonomy_actions_today '
say "EXPORTER=PASS"

[[ "$(container_id jason-runtime)" == "$RUNTIME_BEFORE" ]] || { say "ISOLATION=FAIL runtime changed"; exit 1; }
[[ "$(container_id jason-mcp-pilot)" == "$MCP_BEFORE" ]] || { say "ISOLATION=FAIL mcp changed"; exit 1; }
[[ "$(container_id openbao)" == "$OPENBAO_BEFORE" ]] || { say "ISOLATION=FAIL openbao changed"; exit 1; }
say "CORE_ISOLATION=PASS"

python3 - <<'PY2'
import json,time,urllib.parse,urllib.request
q=urllib.parse.urlencode({'query':'up{job="jason-autonomy-flight-recorder"}'})
for _ in range(25):
    try:
        d=json.load(urllib.request.urlopen('http://127.0.0.1:9090/api/v1/query?'+q,timeout=5))
        if any(r.get('value',[None,'0'])[1]=='1' for r in d.get('data',{}).get('result',[])):
            print('PROMETHEUS_TARGET=UP'); break
    except Exception: pass
    time.sleep(2)
else: raise SystemExit('Prometheus target did not become UP')
PY2

python3 - "$OLD_ENV" <<'PY2'
import base64,json,sys
from pathlib import Path
from urllib.request import Request,urlopen
vals={}
for line in Path(sys.argv[1]).read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); vals[k]=v
user=vals.get('GRAFANA_ADMIN_USER','admin'); password=vals.get('GRAFANA_ADMIN_PASSWORD','')
auth=base64.b64encode(f'{user}:{password}'.encode()).decode()
for path,expected in [('/api/dashboards/uid/jason-autonomy-flight-recorder','jason-autonomy-flight-recorder'),('/api/datasources/uid/jason-autonomy-flight-recorder','jason-autonomy-flight-recorder')]:
    req=Request('http://127.0.0.1:3000'+path,headers={'Authorization':'Basic '+auth})
    with urlopen(req,timeout=5) as resp: payload=json.load(resp)
    uid=(payload.get('dashboard') or payload).get('uid')
    if uid != expected: raise SystemExit(f'Grafana provisioning failed for {path}')
print('GRAFANA_PROVISIONING=PASS')
PY2

say "DEPLOYMENT=PASS"
say "DASHBOARD_UID=jason-autonomy-flight-recorder"
say "EXPORTER=http://127.0.0.1:9475"
say "PROVIDER_ACCESS=NO"
say "PROVIDER_WRITES=NO"
