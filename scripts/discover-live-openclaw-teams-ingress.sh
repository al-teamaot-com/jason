#!/usr/bin/env bash
set -euo pipefail

clear

REPO="/home/al/projects/jason"
OPENCLAW_CONTAINER="openclaw-openclaw-gateway-1"
RUNTIME_CONTAINER="jason-runtime"
OPENCLAW_ROOT="/opt/jason/services/openclaw"

cd "$REPO"

echo "========== START OPENCLAW TEAMS INGRESS DISCOVERY =========="
echo "========== SOURCE STATE =========="
git rev-parse --short HEAD
git status --short

for container in "$OPENCLAW_CONTAINER" "$RUNTIME_CONTAINER"; do
  if ! docker inspect "$container" >/dev/null 2>&1; then
    echo "ERROR: required container is not running: $container"
    exit 20
  fi
done

echo "========== CONTAINER NETWORKS =========="
for container in "$OPENCLAW_CONTAINER" "$RUNTIME_CONTAINER"; do
  echo "--- $container ---"
  docker inspect "$container" --format '{{range $name,$value := .NetworkSettings.Networks}}{{println $name}}{{end}}' | sort -u
  echo
done

echo "========== OPENCLAW EXPOSED PORTS =========="
docker port "$OPENCLAW_CONTAINER" || true

echo "========== OPENCLAW ENVIRONMENT VARIABLE NAMES ONLY =========="
docker inspect "$OPENCLAW_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed 's/=.*$//' \
  | grep -Ei 'JASON|TEAMS|MICROSOFT|BOT|OPENCLAW|GATEWAY|SIGN|KEY|RUNTIME|WEBHOOK|API' \
  | sort -u || true

echo "========== OPENCLAW MOUNTS =========="
docker inspect "$OPENCLAW_CONTAINER" --format '{{range .Mounts}}{{println .Source " -> " .Destination " [" .Mode "]"}}{{end}}' | sort

echo "========== JASON RUNTIME OPENCLAW-RELATED ENV VARIABLE NAMES ONLY =========="
docker inspect "$RUNTIME_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed 's/=.*$//' \
  | grep -Ei 'OPENCLAW|TEAMS|MICROSOFT|SIGN|KEY|INGRESS' \
  | sort -u || true

echo "========== CANDIDATE OPENCLAW SOURCE FILES =========="
if [ -d "$OPENCLAW_ROOT" ]; then
  find "$OPENCLAW_ROOT" -type f \
    \( -name '*.js' -o -name '*.mjs' -o -name '*.cjs' -o -name '*.ts' -o -name '*.tsx' -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' -o -name '*.md' \) \
    2>/dev/null \
    | grep -Ei 'teams|microsoft|jason|gateway|conversation|bot|plugin|extension' \
    | sort \
    | head -n 250
else
  echo "WARN: OpenClaw source root not found at $OPENCLAW_ROOT"
fi

echo "========== CANDIDATE INGRESS REFERENCES IN NON-SECRET SOURCE =========="
if [ -d "$OPENCLAW_ROOT" ]; then
  find "$OPENCLAW_ROOT" -type f \
    \( -name '*.js' -o -name '*.mjs' -o -name '*.cjs' -o -name '*.ts' -o -name '*.tsx' -o -name '*.md' \) \
    -print0 2>/dev/null \
    | xargs -0 grep -nEi \
      'conversation\.turn|jason-runtime|signed.*envelope|key_id|botframework-authenticated|msteams|teams.*conversation|conversation.*teams|/healthz|8080' \
      2>/dev/null \
    | grep -Ev '/node_modules/|/\.git/' \
    | head -n 300 || true
fi

echo "========== OPENCLAW PACKAGE SCRIPTS =========="
for candidate in \
  "$OPENCLAW_ROOT/package.json" \
  "$OPENCLAW_ROOT/openclaw/package.json"; do
  if [ -f "$candidate" ]; then
    echo "--- $candidate ---"
    python3 - "$candidate" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding='utf-8') as handle:
    payload = json.load(handle)
print(json.dumps({
    'name': payload.get('name'),
    'version': payload.get('version'),
    'scripts': payload.get('scripts', {}),
}, indent=2))
PY
  fi
done

echo "========== RESULT =========="
echo "Discovery completed without printing environment values, key material, or secret file contents."
echo "NO REQUESTS WERE SENT."
echo "NO PROVIDER ACTIONS WERE PERFORMED."
echo "NO DEPLOYMENT WAS PERFORMED."
echo "========== END OPENCLAW TEAMS INGRESS DISCOVERY =========="
