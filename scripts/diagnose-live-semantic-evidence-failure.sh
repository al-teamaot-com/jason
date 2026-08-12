#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START LIVE SEMANTIC EVIDENCE FAILURE DIAGNOSTIC =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required."
  exit 20
fi

if ! docker inspect jason-runtime >/dev/null 2>&1; then
  echo "ERROR: jason-runtime container is not available."
  exit 21
fi

echo "========== SECTION 2: RUNTIME STATUS =========="
docker ps --filter name=jason-runtime --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

echo "========== SECTION 3: RECENT SANITIZED RUNTIME ERRORS =========="
TMP_LOG="$(mktemp)"
trap 'rm -f "$TMP_LOG"' EXIT

docker logs --since 30m jason-runtime >"$TMP_LOG" 2>&1 || true

.venv/bin/python - "$TMP_LOG" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(errors="replace")

# Defense in depth: never print authorization material or obvious credential values.
patterns = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:client_secret|secret_id|role_id|access_token|refresh_token|api_key)\s*[:=]\s*)[^\s,;]+"), r"\1[REDACTED]"),
]
for pattern, replacement in patterns:
    text = pattern.sub(replacement, text)

lines = text.splitlines()
needles = (
    "traceback",
    "error",
    "exception",
    "lookuperror",
    "semantic",
    "evidence",
    "processor",
    "display version",
    "display_version",
    "could not safely process",
)

selected = []
for index, line in enumerate(lines):
    lowered = line.casefold()
    if any(needle in lowered for needle in needles):
        start = max(0, index - 3)
        end = min(len(lines), index + 8)
        for candidate in lines[start:end]:
            if candidate not in selected:
                selected.append(candidate)

if not selected:
    print("NOTE: no matching diagnostic lines found in the last 30 minutes.")
else:
    print("\n".join(selected[-250:]))
PY

echo "========== SECTION 4: DEPLOYED SEMANTIC ADAPTER CONTRACT =========="
docker exec jason-runtime python - <<'PY'
from connectors.datto_rmm.semantic_evidence import DATTO_DEVICE_SEMANTIC_FIELDS

for field in DATTO_DEVICE_SEMANTIC_FIELDS:
    print(
        f"FACT={field.canonical_fact} "
        f"CONTEXTS={','.join(field.semantic_contexts)} "
        f"PROVIDER_KEYS={','.join(field.provider_keys)}"
    )
PY

echo "========== SECTION 5: DEPLOYED DIRECT-RESOLUTION CHECK =========="
docker exec jason-runtime python - <<'PY'
from pathlib import Path
import inspect
import orchestrator.resource_evidence as module

source = inspect.getsource(module)
checks = {
    "semantic_evidence_lookup": 'provider_data.get("semantic_evidence")' in source,
    "semantic_pointer_root": '/provider_data/semantic_evidence' in source,
}
for name, value in checks.items():
    print(f"{name}={'PASS' if value else 'FAIL'}")
PY

echo "========== RESULT =========="
echo "Diagnostic complete. No source changes, deployment changes, or provider mutations were performed."
echo "Paste this output back into the working session before making another semantic-evidence code change."
echo "========== END LIVE SEMANTIC EVIDENCE FAILURE DIAGNOSTIC =========="
