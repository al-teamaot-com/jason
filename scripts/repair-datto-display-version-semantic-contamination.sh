#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO DISPLAY VERSION SEMANTIC CONTAMINATION REPAIR =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

BRANCH="$(git branch --show-current)"
if [[ "$BRANCH" != "feature/jason-runtime-service" ]]; then
  echo "ERROR: expected feature/jason-runtime-service; found $BRANCH"
  exit 20
fi

# The repaired read-only diagnostic is the only expected carry-over change from
# the immediately preceding evidence investigation. Preserve it as its own
# durable checkpoint before starting the semantic repair.
UNEXPECTED="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' | grep -v '^ M scripts/diagnose-live-datto-display-version-evidence.sh$' || true)"
if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present before semantic repair."
  printf '%s\n' "$UNEXPECTED"
  exit 21
fi

if git status --porcelain | grep -q '^ M scripts/diagnose-live-datto-display-version-evidence.sh$'; then
  echo "========== SECTION 2: CHECKPOINT REPAIRED READ-ONLY DIAGNOSTIC =========="
  git diff --check -- scripts/diagnose-live-datto-display-version-evidence.sh
  git add scripts/diagnose-live-datto-display-version-evidence.sh
  git commit -m "Fix live Datto evidence diagnostic stdin"

  git fetch origin feature/jason-runtime-service
  LOCAL="$(git rev-parse HEAD)"
  REMOTE="$(git rev-parse origin/feature/jason-runtime-service)"
  BASE="$(git merge-base HEAD origin/feature/jason-runtime-service)"
  if [[ "$BASE" != "$REMOTE" ]]; then
    echo "ERROR: remote branch advanced independently; diagnostic checkpoint not pushed."
    exit 22
  fi
  git push origin feature/jason-runtime-service
  echo "PASS: repaired diagnostic is durable in GitHub at $(git rev-parse --short HEAD)."
else
  echo "========== SECTION 2: CHECKPOINT REPAIRED READ-ONLY DIAGNOSTIC =========="
  echo "NOTE: diagnostic repair is already clean; no diagnostic commit required."
fi

echo "========== SECTION 3: REMOVE FALSE DATTO WINDOWS DISPLAY VERSION ADAPTATION =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/connectors/datto_rmm/semantic_evidence.py")
text = path.read_text()
block = '''    SemanticEvidenceField(\n        canonical_fact="operating system display version",\n        semantic_contexts=("operating_system", "windows_release"),\n        provider_keys=("displayVersion", "DisplayVersion", "display_version", "windowsDisplayVersion"),\n    ),\n'''
if block not in text:
    raise SystemExit("ERROR: expected Datto display-version semantic adapter block was not found")
text = text.replace(block, "", 1)
path.write_text(text)
print(f"UPDATED: {path}")

path = Path("implementation/orchestrator/semantic_knowledge_seed.py")
text = path.read_text()
line = '        "operating_system.windows.display_version": ("displayVersion", "DisplayVersion", "display_version", "windowsDisplayVersion"),\n'
if line not in text:
    raise SystemExit("ERROR: expected Datto display-version provider mapping seed was not found")
text = text.replace(line, "", 1)
path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 4: REPAIR REGRESSION COVERAGE =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/connectors/tests/test_datto_semantic_evidence.py")
text = path.read_text()
old = '''def test_display_version_is_exposed_only_under_os_windows_release_context():\n    adapted = adapt_datto_device_semantic_evidence({\n        "health": {"version": "Unhealthy - Local user changes detected"},\n        "operatingSystem": {"displayVersion": "24H2"},\n    })\n    assert adapted["semantic_evidence"]["operating_system"]["windows_release"]["operating_system_display_version"] == "24H2"\n    assert adapted["health"]["version"] == "Unhealthy - Local user changes detected"\n\n\ndef test_ambiguous_provider_keys_fail_closed_by_omission():\n    adapted = adapt_datto_device_semantic_evidence({\n        "a": {"displayVersion": "23H2"},\n        "b": {"DisplayVersion": "24H2"},\n    })\n    assert "semantic_evidence" not in adapted\n\n\n'''
new = '''def test_datto_display_version_is_not_treated_as_windows_release_evidence():\n    adapted = adapt_datto_device_semantic_evidence({\n        "operatingSystem": "Microsoft Windows 11 Pro 10.0.26200",\n        "cagVersion": "11965",\n        "displayVersion": "4.4.11965.11965",\n    })\n    semantic = adapted.get("semantic_evidence", {})\n    assert "operating_system" not in semantic\n    assert adapted["operatingSystem"] == "Microsoft Windows 11 Pro 10.0.26200"\n    assert adapted["displayVersion"] == "4.4.11965.11965"\n\n\n'''
if old not in text:
    raise SystemExit("ERROR: stale Datto display-version adapter tests were not found")
text = text.replace(old, new, 1)
path.write_text(text)
print(f"UPDATED: {path}")

path = Path("implementation/orchestrator/tests/test_semantic_knowledge_seed.py")
text = path.read_text()
old = '''def test_case_equivalent_provider_aliases_seed_once():\n    registry = build_trusted_semantic_registry()\n    lower = registry.resolve_provider_field(\n        provider="datto_rmm",\n        resource_type="endpoint",\n        provider_field="displayVersion",\n    )\n    upper = registry.resolve_provider_field(\n        provider="datto_rmm",\n        resource_type="endpoint",\n        provider_field="DisplayVersion",\n    )\n    assert lower is not None and upper is not None\n    assert lower.concept_id == "operating_system.windows.display_version"\n    assert upper.concept_id == lower.concept_id\n\n\n'''
new = '''def test_datto_display_version_is_not_seeded_as_windows_release_provider_evidence():\n    registry = build_trusted_semantic_registry()\n    for provider_field in ("displayVersion", "DisplayVersion", "display_version", "windowsDisplayVersion"):\n        assert registry.resolve_provider_field(\n            provider="datto_rmm",\n            resource_type="endpoint",\n            provider_field=provider_field,\n        ) is None\n\n\n'''
if old not in text:
    raise SystemExit("ERROR: stale Datto display-version provider seed test was not found")
text = text.replace(old, new, 1)
path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 5: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 6: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/connectors/tests/test_datto_rmm_connector.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

echo "========== SECTION 7: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "False Datto displayVersion-to-Windows-release semantic contamination removed and validated."
echo "The Windows Display Version human concept remains governed, but Datto no longer claims its agent displayVersion field satisfies that concept."
echo "Datto operatingSystem remains available as raw provider OS evidence; no build-to-release derivation was introduced."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF SEMANTIC REPAIR WORKTREE CHANGES PERFORMED."
echo "========== END DATTO DISPLAY VERSION SEMANTIC CONTAMINATION REPAIR =========="
