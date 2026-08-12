#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CANONICAL ENDPOINT FACT VOCABULARY INSPECTION =========="

echo "========== SECTION 1: SOURCE CHECKPOINT =========="
git log -1 --oneline

echo "========== SECTION 2: ENDPOINT AUDIT CAPABILITY METADATA =========="
grep -n -A65 -B10 'def endpoint_audit_read' implementation/orchestrator/resource_capability_catalog.py || true

echo "========== SECTION 3: NATURAL-LANGUAGE FACT MATCHING =========="
grep -n -A190 -B20 'class MetadataFirstResourceInquiryInterpreter' implementation/orchestrator/conversation_resource_intent.py || true

echo "========== SECTION 4: EVIDENCE LOCATION CONTRACT =========="
grep -n -A190 -B20 'class GovernedResourceEvidenceInterpreter' implementation/orchestrator/resource_evidence.py || true

echo "========== SECTION 5: OLLAMA EVIDENCE REASONER CONTRACT =========="
grep -n -A180 -B30 -E 'ResourceEvidence|evidence.*pointer|requested_facts' implementation/orchestrator/ollama_reasoning.py | head -n 650 || true

echo "========== SECTION 6: DATTO AUDIT NORMALIZATION =========="
grep -n -A220 -B30 -E 'device.audit|get.*audit|audit.*get|processor|physicalMemory|memory|displayVersion|DisplayVersion|operatingSystem|windows' implementation/connectors/datto_rmm/connector.py | head -n 800 || true

echo "========== SECTION 7: EXISTING FACT TEST COVERAGE =========="
grep -R -n -A55 -B12 -E 'processor|cpu|memory|ram|display.?version|windows.*version|operating.?system' \
  implementation/orchestrator/tests implementation/connectors/tests implementation/runtime_service/tests \
  2>/dev/null | head -n 900 || true

echo "========== SECTION 8: LIVE DATTO AUDIT SHAPE FOR AOT-50282 =========="
cat <<'NOTE'
The next output intentionally prints field names and non-secret audit values only.
It must not print credentials, tokens, or secret material.
NOTE

export PYTHONPATH="/home/al/projects/jason/implementation:/home/al/projects/jason/implementation/connectors/src:/home/al/projects/jason/implementation/connectors/openclaw/src:/home/al/projects/jason/implementation/runtime_service/src"

python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

# We use the already-running runtime only as the authority for secret-path metadata.
# Secret values are never printed.
try:
    import subprocess
    env_text = subprocess.check_output(
        ["docker", "inspect", "jason-runtime", "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
        text=True,
    )
except Exception as exc:
    print(f"LIVE_SHAPE_SKIPPED: unable to inspect running runtime environment: {exc}")
    raise SystemExit(0)

for line in env_text.splitlines():
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.startswith("JASON_") and key.endswith("_HOST_PATH"):
        os.environ.setdefault(key, value)

# Prefer an existing project proof/helper if one already knows how to construct the
# live Datto connector. We deliberately do not recreate credential plumbing here.
candidates = [
    Path("scripts/prove-live-site-outcome-contract.sh"),
    Path("scripts/patch-canonical-collection-facts.sh"),
]
print("AVAILABLE_LIVE_HELPERS:", ", ".join(str(p) for p in candidates if p.exists()))
print("LIVE_AUDIT_SHAPE_REQUIRES_EXISTING_CONNECTOR_BOOTSTRAP: TRUE")
print("TARGET: AOT-50282 / datto_rmm.device.audit.get")
PY

echo "========== RESULT =========="
echo "Read-only canonical endpoint fact vocabulary inspection complete."
echo "No source changes performed."
echo "========== END CANONICAL ENDPOINT FACT VOCABULARY INSPECTION =========="
