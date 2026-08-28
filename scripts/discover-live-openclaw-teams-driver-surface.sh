#!/usr/bin/env bash
set -euo pipefail

clear

OPENCLAW_ROOT="/opt/jason/services/openclaw"
OPENCLAW_CONTAINER="openclaw-openclaw-gateway-1"

cd /home/al/projects/jason

echo "========== START TARGETED TEAMS DRIVER SURFACE DISCOVERY =========="
echo "========== SOURCE STATE =========="
git rev-parse --short HEAD
git status --short

echo "========== OPENCLAW PORT ENV VALUES (NON-SECRET) =========="
docker inspect "$OPENCLAW_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(OPENCLAW_(BRIDGE_PORT|GATEWAY_PORT|GATEWAY_BIND)|PORT)=' || true

echo "========== LISTENERS INSIDE OPENCLAW CONTAINER =========="
docker exec "$OPENCLAW_CONTAINER" sh -lc '
  if command -v ss >/dev/null 2>&1; then ss -lntp; 
  elif command -v netstat >/dev/null 2>&1; then netstat -lntp; 
  else echo "No ss/netstat available"; fi
' 2>/dev/null || true

echo "========== TEAMS-RELATED RUNTIME CONFIG FILES =========="
find "$OPENCLAW_ROOT/data/config" "$OPENCLAW_ROOT/data/workspace" \
  -maxdepth 6 -type f \
  \( -name '*.json' -o -name '*.jsonc' -o -name '*.yaml' -o -name '*.yml' -o -name '*.toml' -o -name '*.md' \) \
  2>/dev/null \
  | while IFS= read -r f; do
      if grep -qiE 'msteams|microsoft[ _-]?teams|botframework|3978|conversation\.turn|jason-runtime' "$f" 2>/dev/null; then
        echo "$f"
      fi
    done \
  | head -120

echo "========== TARGETED CONFIG REFERENCES (VALUES REDACTED WHERE SENSITIVE) =========="
find "$OPENCLAW_ROOT/data/config" "$OPENCLAW_ROOT/data/workspace" \
  -maxdepth 6 -type f \
  \( -name '*.json' -o -name '*.jsonc' -o -name '*.yaml' -o -name '*.yml' -o -name '*.toml' -o -name '*.md' \) \
  2>/dev/null \
  | while IFS= read -r f; do
      matches="$(grep -nEi 'msteams|microsoft[ _-]?teams|botframework|3978|conversation\.turn|jason-runtime|callback|webhook|endpoint|route|path' "$f" 2>/dev/null | head -40 || true)"
      if [ -n "$matches" ]; then
        echo "--- $f ---"
        printf '%s\n' "$matches" \
          | sed -E 's/((token|secret|password|client_secret|appPassword|app_password)[^:=]*[:=])[[:space:]]*[^, }]+/\1 <redacted>/Ig'
      fi
    done \
  | head -400

echo "========== OPENCLAW SOURCE FILES WITH TEAMS/BOTFRAMEWORK ROUTES =========="
grep -RIlE 'msteams|microsoft[ _-]?teams|botframework|3978|conversation\.turn' \
  "$OPENCLAW_ROOT/src" "$OPENCLAW_ROOT/extensions" "$OPENCLAW_ROOT/packages" \
  2>/dev/null \
  | head -120 || true

echo "========== TARGETED SOURCE REFERENCES =========="
grep -RInE 'msteams|microsoft[ _-]?teams|botframework|3978|conversation\.turn|listen\(|router\.|app\.(post|get)|/api/|/messages|callback|webhook' \
  "$OPENCLAW_ROOT/src" "$OPENCLAW_ROOT/extensions" "$OPENCLAW_ROOT/packages" \
  2>/dev/null \
  | grep -Ei 'teams|botframework|3978|conversation\.turn|/messages|jason' \
  | head -400 || true

echo "========== MICROSOFT TEAMS SECRET FILENAMES ONLY =========="
find /opt/jason/bootstrap/secrets/microsoft-teams -maxdepth 2 -type f -printf '%f\n' 2>/dev/null | sort || true

echo "========== JASON RUNTIME HTTP/INGRESS REFERENCES =========="
grep -RInE 'conversation\.turn|openclaw|teams|msteams|/healthz|do_POST|path|route' \
  /home/al/projects/jason/implementation/runtime_service \
  /home/al/projects/jason/implementation/connectors/openclaw \
  2>/dev/null \
  | head -300 || true

echo "========== RESULT =========="
echo "Discovery only. No messages were sent and no secret values were printed."
echo "========== END TARGETED TEAMS DRIVER SURFACE DISCOVERY =========="
