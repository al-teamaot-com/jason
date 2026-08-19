#!/usr/bin/env bash
set -euo pipefail

clear

ROOT="/opt/jason/services/openclaw"
CONFIG="$ROOT/data/config/openclaw.json"
BRIDGE="$ROOT/data/config/extensions/jason-bridge/openclaw.plugin.json"
MSTEAMS="$ROOT/data/config/npm/projects/openclaw-msteams-d29647a7c0/node_modules/@openclaw/msteams"

echo "========== START LIVE TEAMS ROUTE DISCOVERY =========="

echo "========== OPENCLAW TOP-LEVEL CONFIG KEYS =========="
if [ -f "$CONFIG" ]; then
  python3 - "$CONFIG" <<'PY'
import json, sys
p=sys.argv[1]
data=json.load(open(p, encoding='utf-8'))
for key in sorted(data):
    print(key)
PY
else
  echo "MISSING: $CONFIG"
fi

echo "========== TEAMS CONFIG SHAPE (VALUES REDACTED) =========="
if [ -f "$CONFIG" ]; then
  python3 - "$CONFIG" <<'PY'
import json, sys
p=sys.argv[1]
data=json.load(open(p, encoding='utf-8'))

def walk(obj, path=()):
    if isinstance(obj, dict):
        for k,v in obj.items():
            kp=path+(str(k),)
            low='.'.join(kp).lower()
            if 'team' in low or 'msteams' in low or 'jason' in low or 'bridge' in low:
                if isinstance(v, (dict,list)):
                    print('.'.join(kp), type(v).__name__)
                else:
                    print('.'.join(kp), '<redacted>')
            walk(v,kp)
    elif isinstance(obj,list):
        for i,v in enumerate(obj):
            walk(v,path+(str(i),))
walk(data)
PY
fi

echo "========== JASON BRIDGE MANIFEST (NON-SECRET FIELDS) =========="
if [ -f "$BRIDGE" ]; then
  python3 - "$BRIDGE" <<'PY'
import json, sys
p=sys.argv[1]
data=json.load(open(p, encoding='utf-8'))
for key in sorted(data):
    value=data[key]
    if any(token in key.lower() for token in ('secret','token','key','password','credential')):
        print(f"{key}=<redacted>")
    elif isinstance(value, (str,int,float,bool)) or value is None:
        print(f"{key}={value}")
    else:
        print(f"{key}=<{type(value).__name__}>")
PY
else
  echo "MISSING: $BRIDGE"
fi

echo "========== JASON BRIDGE RUNTIME FILES =========="
find "$ROOT/data/config/extensions/jason-bridge" -maxdepth 2 -type f -print 2>/dev/null | sort || true

echo "========== SEARCH TOOL =========="
if command -v rg >/dev/null 2>&1; then
  echo "Using rg"
  SEARCH_TOOL="rg"
else
  echo "rg not installed; using grep fallback"
  SEARCH_TOOL="grep"
fi

echo "========== MSTEAMS ROUTE REFERENCES =========="
if [ -d "$MSTEAMS" ]; then
  if [ "$SEARCH_TOOL" = "rg" ]; then
    rg -n --glob '!**/*.map' --glob '!**/*.d.ts' \
      '3978|messages|api/messages|listen\(|router|route\(|app\.post|server\.post|BotFramework|botframework' \
      "$MSTEAMS" 2>/dev/null | head -200 || true
  else
    grep -RniE \
      --exclude='*.map' --exclude='*.d.ts' \
      '3978|messages|api/messages|listen\(|router|route\(|app\.post|server\.post|BotFramework|botframework' \
      "$MSTEAMS" 2>/dev/null | head -200 || true
  fi
else
  echo "MISSING: $MSTEAMS"
fi

echo "========== JASON BRIDGE REFERENCES =========="
BRIDGE_DIR="$ROOT/data/config/extensions/jason-bridge"
if [ -d "$BRIDGE_DIR" ]; then
  if [ "$SEARCH_TOOL" = "rg" ]; then
    rg -n \
      'jason-runtime|8080|conversation\.turn|msteams|teams|fetch\(|http://|https://|correlation|signature|key_id' \
      "$BRIDGE_DIR" 2>/dev/null | head -240 || true
  else
    grep -RniE \
      'jason-runtime|8080|conversation\.turn|msteams|teams|fetch\(|http://|https://|correlation|signature|key_id' \
      "$BRIDGE_DIR" 2>/dev/null | head -240 || true
  fi
else
  echo "MISSING: $BRIDGE_DIR"
fi

echo "========== RECENT OPENCLAW ROUTE LOG HINTS =========="
if [ "$SEARCH_TOOL" = "rg" ]; then
  docker logs --since 30m openclaw-openclaw-gateway-1 2>&1 \
    | rg -i 'msteams|teams|3978|jason|bridge|conversation|message' \
    | tail -120 || true
else
  docker logs --since 30m openclaw-openclaw-gateway-1 2>&1 \
    | grep -Ei 'msteams|teams|3978|jason|bridge|conversation|message' \
    | tail -120 || true
fi

echo "========== END LIVE TEAMS ROUTE DISCOVERY =========="
