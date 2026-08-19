#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO DISPLAY VERSION SEMANTIC REPAIR DEPLOYMENT =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before deployment."
  printf '%s\n' "$DIRTY"
  exit 20
fi

if ! docker ps --format '{{.Names}}' | grep -qx 'jason-runtime'; then
  echo "ERROR: jason-runtime is not currently running."
  exit 21
fi

echo "========== SECTION 2: DERIVE CURRENT RUNTIME INPUTS WITHOUT PRINTING SECRETS =========="
python3 - <<'PY' > /tmp/jason-semantic-repair-env.sh
import json, subprocess, shlex

container = json.loads(subprocess.check_output(["docker", "inspect", "jason-runtime"], text=True))[0]

env = {}
for item in container.get("Config", {}).get("Env", []):
    if "=" in item:
        k, v = item.split("=", 1)
        env[k] = v

required_env = ["JASON_OLLAMA_MODEL"]
for key in required_env:
    value = env.get(key, "").strip()
    if not value:
        raise SystemExit(f"missing required runtime env: {key}")
    print(f"export {key}={shlex.quote(value)}")

required_targets = {
    "/run/jason-secrets/openbao/role_id": "JASON_OPENBAO_ROLE_ID_HOST_PATH",
    "/run/jason-secrets/openbao/secret_id": "JASON_OPENBAO_SECRET_ID_HOST_PATH",
    "/run/jason-secrets/openbao/microsoft-graph/role_id": "JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH",
    "/run/jason-secrets/openbao/microsoft-graph/secret_id": "JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH",
    "/run/jason-secrets/openbao/aws-ses/role_id": "JASON_SES_OPENBAO_ROLE_ID_HOST_PATH",
    "/run/jason-secrets/openbao/aws-ses/secret_id": "JASON_SES_OPENBAO_SECRET_ID_HOST_PATH",
}
mounts = {m.get("Destination"): m.get("Source") for m in container.get("Mounts", [])}
for destination, export_name in required_targets.items():
    source = (mounts.get(destination) or "").strip()
    if not source:
        raise SystemExit(f"missing current secret mount source for {destination}")
    print(f"export {export_name}={shlex.quote(source)}")
PY
# shellcheck disable=SC1091
source /tmp/jason-semantic-repair-env.sh
rm -f /tmp/jason-semantic-repair-env.sh

echo "PASS: derived current model identifier and six secret host-path references from running runtime metadata."
echo "NOTE: secret contents were not read or printed."

echo "========== SECTION 3: VALIDATE COMPOSE =========="
cd infrastructure/jason-runtime
docker compose config >/dev/null

echo "========== SECTION 4: BUILD RUNTIME IMAGE =========="
docker compose build jason-runtime

echo "========== SECTION 5: RECREATE RUNTIME =========="
docker compose up -d --force-recreate jason-runtime

echo "========== SECTION 6: BOUNDED HEALTH CHECK =========="
for attempt in $(seq 1 30); do
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' jason-runtime 2>/dev/null || true)"
  echo "health[$attempt]=$state"
  if [[ "$state" == "healthy" ]]; then
    echo "PASS: jason-runtime is healthy."
    break
  fi
  if [[ "$state" == "unhealthy" || "$state" == "exited" || "$state" == "dead" ]]; then
    echo "ERROR: jason-runtime entered failure state: $state"
    exit 30
  fi
  sleep 2
  if [[ "$attempt" -eq 30 ]]; then
    echo "ERROR: jason-runtime did not become healthy within bounded wait."
    exit 31
  fi
done

echo "========== SECTION 7: DEPLOYED CONTAMINATION GUARD CHECK =========="
docker exec -i jason-runtime python - <<'PY'
from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry

payload = {
    "operatingSystem": "Microsoft Windows 11 Pro 10.0.26200",
    "displayVersion": "4.4.11965.11965",
    "cagVersion": "11965",
}
adapted = adapt_datto_device_semantic_evidence(payload)
semantic = adapted.get("semantic_evidence", {})
windows = semantic.get("operating_system", {}) if isinstance(semantic, dict) else {}
release = windows.get("windows_release", {}) if isinstance(windows, dict) else {}
if "operating_system_display_version" in release:
    raise SystemExit("FAIL: Datto displayVersion still contaminates Windows Display Version semantics")

registry = build_trusted_semantic_registry()
if registry.resolve_provider_field(
    provider="datto_rmm",
    resource_type="endpoint",
    provider_field="displayVersion",
) is not None:
    raise SystemExit("FAIL: Datto displayVersion remains an active provider-field semantic mapping")

concept = registry.resolve_term("Windows Display Version")
if concept is None or concept.concept_id != "operating_system.windows.display_version":
    raise SystemExit("FAIL: governed Windows Display Version human concept is missing")

print("PASS: Datto displayVersion does not satisfy Windows Display Version semantics.")
print("PASS: human Windows Display Version concept remains governed and active.")
PY

echo "========== FINAL STATUS =========="
docker ps --filter name='^jason-runtime$' --format 'NAMES\tSTATUS\tIMAGE'
echo "PASS: Datto display-version semantic repair deployed and verified."
echo "Next: retry the live Teams Windows Display Version question."
echo "========== END DATTO DISPLAY VERSION SEMANTIC REPAIR DEPLOYMENT =========="
