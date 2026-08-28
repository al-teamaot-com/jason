#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY PRODUCTION RUNTIME DEPLOYMENT =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before deployment."
  printf '%s\n' "$DIRTY"
  exit 20
fi

if ! docker ps --format '{{.Names}}' | grep -qx 'jason-runtime'; then
  echo "ERROR: jason-runtime container is not running; cannot safely derive current deployment inputs."
  exit 21
fi

COMPOSE_DIR="/home/al/projects/jason/infrastructure/jason-runtime"
COMPOSE_FILE="$COMPOSE_DIR/compose.yaml"
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: compose file not found: $COMPOSE_FILE"
  exit 22
fi

TMP_ENV="$(mktemp)"
cleanup() {
  rm -f "$TMP_ENV"
}
trap cleanup EXIT

echo "========== SECTION 2: DERIVE CURRENT RUNTIME INPUTS WITHOUT PRINTING SECRETS =========="
.venv/bin/python - "$TMP_ENV" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

out = Path(sys.argv[1])
raw = subprocess.check_output(["docker", "inspect", "jason-runtime"], text=True)
obj = json.loads(raw)[0]
env = {}
for item in obj.get("Config", {}).get("Env", []):
    if "=" not in item:
        continue
    k, v = item.split("=", 1)
    env[k] = v

required_env = ["JASON_OLLAMA_MODEL"]
missing = [k for k in required_env if not env.get(k)]
if missing:
    raise SystemExit("ERROR: running runtime missing required env metadata: " + ",".join(missing))

mount_by_dest = {
    m.get("Destination"): m.get("Source")
    for m in obj.get("Mounts", [])
    if m.get("Destination") and m.get("Source")
}
required_mounts = {
    "JASON_OPENBAO_ROLE_ID_HOST_PATH": "/run/jason-secrets/openbao/role_id",
    "JASON_OPENBAO_SECRET_ID_HOST_PATH": "/run/jason-secrets/openbao/secret_id",
    "JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH": "/run/jason-secrets/openbao/microsoft-graph/role_id",
    "JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH": "/run/jason-secrets/openbao/microsoft-graph/secret_id",
    "JASON_SES_OPENBAO_ROLE_ID_HOST_PATH": "/run/jason-secrets/openbao/aws-ses/role_id",
    "JASON_SES_OPENBAO_SECRET_ID_HOST_PATH": "/run/jason-secrets/openbao/aws-ses/secret_id",
}
resolved = {"JASON_OLLAMA_MODEL": env["JASON_OLLAMA_MODEL"]}
for key, dest in required_mounts.items():
    source = mount_by_dest.get(dest)
    if not source:
        raise SystemExit(f"ERROR: running runtime missing required mount metadata for {dest}")
    resolved[key] = source

with out.open("w", encoding="utf-8") as handle:
    for key, value in resolved.items():
        handle.write(f"{key}={value}\n")

print("PASS: derived current model identifier and six secret host-path references from running runtime metadata.")
print("NOTE: secret contents were not read or printed.")
PY

set -a
# shellcheck disable=SC1090
source "$TMP_ENV"
set +a

echo "========== SECTION 3: VALIDATE COMPOSE =========="
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo "========== SECTION 4: BUILD RUNTIME IMAGE =========="
docker compose -f "$COMPOSE_FILE" build jason-runtime

echo "========== SECTION 5: RECREATE RUNTIME =========="
docker compose -f "$COMPOSE_FILE" up -d --force-recreate jason-runtime

echo "========== SECTION 6: BOUNDED HEALTH CHECK =========="
for attempt in $(seq 1 30); do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' jason-runtime 2>/dev/null || true)"
  echo "health[$attempt]=$status"
  if [[ "$status" == "healthy" ]]; then
    echo "PASS: jason-runtime is healthy."
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "ERROR: jason-runtime did not become healthy within the bounded wait."
    docker ps --filter name=jason-runtime --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
    exit 23
  fi
  sleep 2
done

echo "========== SECTION 7: DEPLOYED SEMANTIC WIRING CHECK =========="
docker exec -i jason-runtime python - <<'PY'
from orchestrator.semantic_fact_resolver import SemanticFactResolver
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry

resolver = SemanticFactResolver(registry=build_trusted_semantic_registry())
checks = {
    "CPU": "processor.model",
    "RAM": "memory.total",
    "Windows Display Version": "operating_system.windows.display_version",
    "BIOS": "firmware.bios.version",
}
for term, expected in checks.items():
    result = resolver.resolve(term)
    if result is None or result.concept_id != expected:
        raise SystemExit(f"ERROR: deployed semantic registry resolution failed for {term}")
    print(f"PASS: {term} -> {result.concept_id}")
PY

echo "========== FINAL STATUS =========="
docker ps --filter name=jason-runtime --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
echo "PASS: semantic-registry-backed production runtime deployed and healthy."
echo "Next: run live Teams acceptance probes for CPU, RAM, Windows Display Version, and person-to-endpoint semantics."
echo "========== END SEMANTIC REGISTRY PRODUCTION RUNTIME DEPLOYMENT =========="
