#!/usr/bin/env bash
set -euo pipefail

ROOT="${JASON_REPO_ROOT:-/home/al/projects/jason}"
SHOWCASE="$ROOT/infrastructure/showcase"
SERVICE_SRC="$SHOWCASE/systemd/jason-toner-exporter.service"
USER_SYSTEMD="$HOME/.config/systemd/user"
STATE_DIR="$HOME/.local/state/jason/toner-intelligence"

cd "$ROOT"
python3 -m unittest infrastructure/showcase/tests/test_toner_intelligence.py
python3 -m py_compile infrastructure/toner-intelligence/*.py
python3 -m json.tool infrastructure/showcase/grafana/dashboards/jason-toner-readiness.json >/dev/null
docker run --rm --entrypoint=promtool -v "$SHOWCASE/prometheus/prometheus.yml:/tmp/prometheus.yml:ro" prom/prometheus:v3.7.3 check config /tmp/prometheus.yml >/tmp/jason-toner-prometheus-check.txt

install -d -m 0750 "$STATE_DIR"
install -d -m 0755 "$USER_SYSTEMD"
install -m 0644 "$SERVICE_SRC" "$USER_SYSTEMD/jason-toner-exporter.service"
systemctl --user daemon-reload
systemctl --user enable --now jason-toner-exporter.service

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:9473/metrics >/tmp/jason-toner-live.prom; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:9473/metrics >/tmp/jason-toner-live.prom
docker exec -i jason-prometheus promtool check metrics </tmp/jason-toner-live.prom
curl -fsS -X POST http://127.0.0.1:9090/-/reload >/dev/null

docker exec jason-grafana test -r /var/lib/grafana/dashboards/jason-toner-readiness.json
python3 - <<'PY'
import json, time, urllib.request
url='http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22jason-toner%22%7D'
for _ in range(30):
    try:
        data=json.load(urllib.request.urlopen(url,timeout=2))
        rows=data.get('data',{}).get('result',[])
        if rows and rows[0].get('value',[None,'0'])[1]=='1':
            print('jason-toner Prometheus target: UP')
            raise SystemExit(0)
    except Exception:
        pass
    time.sleep(1)
raise SystemExit('jason-toner Prometheus target did not become UP')
PY

echo 'Toner readiness production observability deployment complete.'
