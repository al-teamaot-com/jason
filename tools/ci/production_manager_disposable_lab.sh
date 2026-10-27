#!/usr/bin/env bash
set -euo pipefail
# Disposable GitHub-hosted Ubuntu runner only. Never run on Jason production.
test "$GITHUB_ACTIONS" = true
test "$JASON_PM_LAB" = 1
test "$(id -u)" -eq 0
test -d /run/systemd/system
test ! -e /opt/jason/current
test ! -e /var/lib/jason/openclaw
test ! -e /home/al/projects/jason
test -n "$GITHUB_WORKSPACE"
test -n "$EVIDENCE_OUTPUT"
cd "$GITHUB_WORKSPACE"
docker info >/dev/null
BASE=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CAND=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
DIR="$(mktemp -d /tmp/jason-pm-lab-XXXXXXXX)"
BASEUNIT=jason-pm-lab-baseline.service
CANDUNIT=jason-pm-lab-candidate.service
TIMER=jason-pm-lab-candidate.timer
UNITDIR=/etc/systemd/system
IMAGE=jason-pm-lab-candidate:scenario
for unit in "$BASEUNIT" "$CANDUNIT" "$TIMER"; do test ! -e "$UNITDIR/$unit"; done
for name in jason-pm-lab-runtime jason-pm-lab-mcp jason-pm-lab-runtime-rollback jason-pm-lab-mcp-rollback; do
  if docker inspect "$name" >/dev/null 2>&1; then echo "ABORT existing lab container" >&2; exit 2; fi
done
cleanup() {
  systemctl disable --now "$TIMER" >/dev/null 2>&1 || true
  systemctl stop "$CANDUNIT" "$BASEUNIT" >/dev/null 2>&1 || true
  rm -f "$UNITDIR/$BASEUNIT" "$UNITDIR/$CANDUNIT" "$UNITDIR/$TIMER"
  systemctl daemon-reload >/dev/null 2>&1 || true
  for name in jason-pm-lab-runtime jason-pm-lab-mcp jason-pm-lab-runtime-rollback jason-pm-lab-mcp-rollback; do
    docker rm -f "$name" >/dev/null 2>&1 || true
  done
  docker image rm "$IMAGE" >/dev/null 2>&1 || true
  rm -rf "$DIR"
}
trap cleanup EXIT

mkdir -p "$DIR/releases/$BASE/config" "$DIR/releases/$CAND/config" "$DIR/releases/$CAND/infrastructure/openclaw-operations/systemd"
cat > "$DIR/releases/$BASE/config/production-desired-state.json" <<'EOF'
{"schema_version":"1.0","required_system_units":["jason-pm-lab-baseline.service"],"allowed_system_units":[],"required_user_units":[],"allowed_user_units":[]}
EOF
cat > "$DIR/releases/$CAND/config/production-desired-state.json" <<'EOF'
{"schema_version":"1.0","required_system_units":["jason-pm-lab-baseline.service"],"allowed_system_units":["jason-pm-lab-candidate.service","jason-pm-lab-candidate.timer"],"required_user_units":[],"allowed_user_units":[]}
EOF
cat > "$UNITDIR/$BASEUNIT" <<'EOF'
[Unit]
Description=Disposable Jason PM baseline only
[Service]
Type=oneshot
ExecStart=/usr/bin/true
RemainAfterExit=yes
EOF
cat > "$DIR/releases/$CAND/infrastructure/openclaw-operations/systemd/$CANDUNIT" <<'EOF'
[Unit]
Description=Disposable Jason PM candidate only
[Service]
Type=oneshot
ExecStart=/usr/bin/true
RemainAfterExit=yes
EOF
cat > "$DIR/releases/$CAND/infrastructure/openclaw-operations/systemd/$TIMER" <<'EOF'
[Unit]
Description=Disposable Jason PM candidate timer only
[Timer]
OnUnitActiveSec=1h
Unit=jason-pm-lab-candidate.service
[Install]
WantedBy=timers.target
EOF
cp "$DIR/releases/$CAND/infrastructure/openclaw-operations/systemd/$CANDUNIT" "$UNITDIR/$CANDUNIT"
cp "$DIR/releases/$CAND/infrastructure/openclaw-operations/systemd/$TIMER" "$UNITDIR/$TIMER"
BASEHASH="$(sha256sum "$UNITDIR/$BASEUNIT" | cut -d' ' -f1)"
systemctl daemon-reload
systemctl start "$BASEUNIT" "$CANDUNIT"
systemctl enable --now "$TIMER"
systemctl is-active --quiet "$BASEUNIT"
systemctl is-active --quiet "$TIMER"

# Fail closed on a tampered candidate-only root service definition.
printf '\n# unexpected modification\n' >> "$UNITDIR/$CANDUNIT"
python3 - "$DIR/releases/$CAND" "$DIR/releases/$BASE" "$UNITDIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,"tools")
from reconcile_managed_unit_delta import UnitDeltaError,plan_unit_removals
try:
    plan_unit_removals(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),scope="system",enforce_owner=True)
except UnitDeltaError as error:
    assert "differs from candidate" in str(error),str(error)
    print("SCENARIO_C_ROOT_TAMPER_DENIAL=PASS")
else:
    raise AssertionError("root unit tamper not rejected")
PY
cp "$DIR/releases/$CAND/infrastructure/openclaw-operations/systemd/$CANDUNIT" "$UNITDIR/$CANDUNIT"

# Canonical planner returns exactly the two candidate-only units.
python3 - "$DIR/releases/$CAND" "$DIR/releases/$BASE" "$UNITDIR" > "$DIR/removals" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,"tools")
from reconcile_managed_unit_delta import plan_unit_removals
for unit in plan_unit_removals(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),scope="system",enforce_owner=True):
    print(unit)
PY
test "$(wc -l < "$DIR/removals")" -eq 2
grep -Fx "$TIMER" "$DIR/removals"
grep -Fx "$CANDUNIT" "$DIR/removals"
systemctl disable --now "$TIMER"
systemctl stop "$CANDUNIT"
while IFS= read -r unit; do rm "$UNITDIR/$unit"; done < "$DIR/removals"
systemctl daemon-reload
test ! -e "$UNITDIR/$TIMER"
test ! -e "$UNITDIR/$CANDUNIT"
test "$(sha256sum "$UNITDIR/$BASEUNIT" | cut -d' ' -f1)" = "$BASEHASH"
systemctl is-active --quiet "$BASEUNIT"
echo "SCENARIO_B_SYSTEMD_DELTA_ROLLBACK=PASS"

# Two actual Docker-helper failure/rollback cycles with no network/ports/mounts.
docker pull python:3.12-alpine >/dev/null
docker build --quiet --tag "$IMAGE" - <<'EOF'
FROM python:3.12-alpine
RUN echo lab-candidate > /tmp/lab-marker
EOF
for name in jason-pm-lab-runtime jason-pm-lab-mcp; do
  docker run --detach --name "$name" --network none \
    --label "com.teamaot.jason.source_revision=$BASE" \
    --env "JASON_SOURCE_REVISION=$BASE" python:3.12-alpine python -m http.server 8080 >/dev/null
  sleep 2
  docker exec "$name" python -c "import urllib.request;assert urllib.request.urlopen('http://127.0.0.1:8080/',timeout=4).status==200"
  OLDID="$(docker inspect "$name" --format '{{.Id}}')"
  OLDIMAGE="$(docker inspect "$name" --format '{{.Image}}')"
  if python3 tools/deploy_live_container.py --live "$name" --image "$IMAGE" \
      --rollback "$name-rollback" --source-revision "$CAND" \
      --health-url http://127.0.0.1:65535/injected-failure \
      --health-attempts 1 --health-interval 0; then
    echo "FAIL unhealthy candidate wrongly accepted" >&2
    exit 1
  fi
  test "$(docker inspect "$name" --format '{{.Id}}')" = "$OLDID"
  test "$(docker inspect "$name" --format '{{.Image}}')" = "$OLDIMAGE"
  test "$(docker inspect "$name" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}')" = "$BASE"
  docker exec "$name" python -c "import urllib.request;assert urllib.request.urlopen('http://127.0.0.1:8080/',timeout=4).status==200"
  if docker inspect "$name-rollback" >/dev/null 2>&1; then echo "FAIL rollback container retained" >&2; exit 1; fi
  printf 'SCENARIO_A_%s_EXACT_ROLLBACK=PASS\n' "$name"
done

python3 - "$EVIDENCE_OUTPUT" "$BASE" "$CAND" "$BASEHASH" <<'PY'
import json,os,pathlib,sys
from datetime import datetime,timezone
p=pathlib.Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True)
o={"schema_version":"1.0","environment":"ephemeral GitHub-hosted Ubuntu systemd/Docker",
   "production_credentials_used":False,"production_resources_touched":False,
   "baseline_revision":sys.argv[2],"candidate_revision":sys.argv[3],
   "baseline_unit_hash":sys.argv[4],"shadow_breaker":"OPEN_after_injected_failure",
   "shadow_known_good":sys.argv[2],
   "tests":{"runtime_exact_id_image_rollback":"PASS","mcp_exact_id_image_rollback":"PASS",
            "candidate_only_systemd_timer_service_removed":"PASS","tampered_unit_rejected":"PASS",
            "baseline_systemd_and_http_reverified":"PASS"},
   "limitations":["Does not run full native root release-control bridge or host reconciliation.",
                  "Does not replace all stage-2 acceptance of #1581.",
                  "Does not authorize a production deployment."],
   "recorded_at":datetime.now(timezone.utc).isoformat()}
with p.open("x",encoding="utf-8") as f:
    json.dump(o,f,indent=2,sort_keys=True);f.write("\n")
os.chmod(p,0o644)
print("ISOLATED_LAB=PASS_WITH_EXPLICIT_LIMITATIONS")
PY
