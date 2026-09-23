#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START GOVERNED WINDOWS BUILD TO RELEASE DERIVATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ADD GOVERNED DERIVATION FOUNDATION =========="
"$PY" - <<'PY'
from pathlib import Path

root = Path('/home/al/projects/jason')
module = root / 'implementation/orchestrator/semantic_derivations.py'
tests = root / 'implementation/orchestrator/tests/test_semantic_derivations.py'

module.write_text('''from __future__ import annotations\n\nfrom dataclasses import dataclass\nimport re\n\n\n@dataclass(frozen=True, slots=True)\nclass DerivedSemanticFact:\n    concept_id: str\n    canonical_label: str\n    value: str\n    source_fact: str\n    source_value: str\n    authority: str\n    authority_reference: str\n    rule_version: str\n\n\nWINDOWS_RELEASE_AUTHORITY = "Microsoft Windows 11 release information"\nWINDOWS_RELEASE_AUTHORITY_REFERENCE = "https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information"\nWINDOWS_BUILD_RELEASE_RULE_VERSION = "2026-08-13"\n\n# Governed mappings are intentionally explicit and narrow. These are build families\n# documented by Microsoft, not guesses from product names or provider field names.\n_WINDOWS_11_BUILD_FAMILY_TO_RELEASE = {\n    22631: "23H2",\n    26100: "24H2",\n    26200: "25H2",\n    28000: "26H1",\n}\n\n\ndef derive_windows_display_version_from_operating_system(\n    operating_system_value: object,\n) -> DerivedSemanticFact | None:\n    \"\"\"Derive Windows release version only from an explicit OS build family.\n\n    The input must be provider evidence that itself names Windows and carries an OS\n    build token. Unknown build families remain unresolved. No language model or\n    provider-specific displayVersion field participates in this derivation.\n    \"\"\"\n    if not isinstance(operating_system_value, str):\n        return None\n    text = operating_system_value.strip()\n    if not text or "windows" not in text.casefold():\n        return None\n\n    matches = re.findall(r"(?<!\\d)(\\d{5})(?:\\.\\d+)?(?!\\d)", text)\n    families = {int(match) for match in matches if int(match) in _WINDOWS_11_BUILD_FAMILY_TO_RELEASE}\n    if len(families) != 1:\n        return None\n    family = next(iter(families))\n    release = _WINDOWS_11_BUILD_FAMILY_TO_RELEASE[family]\n    return DerivedSemanticFact(\n        concept_id="operating_system.windows.display_version",\n        canonical_label="operating system display version",\n        value=release,\n        source_fact="operating system",\n        source_value=text,\n        authority=WINDOWS_RELEASE_AUTHORITY,\n        authority_reference=WINDOWS_RELEASE_AUTHORITY_REFERENCE,\n        rule_version=WINDOWS_BUILD_RELEASE_RULE_VERSION,\n    )\n''', encoding='utf-8')


tests.write_text('''from orchestrator.semantic_derivations import derive_windows_display_version_from_operating_system\n\n\ndef test_windows_26200_derives_25h2():\n    fact = derive_windows_display_version_from_operating_system(\n        "Microsoft Windows 11 Pro 10.0.26200"\n    )\n    assert fact is not None\n    assert fact.concept_id == "operating_system.windows.display_version"\n    assert fact.value == "25H2"\n    assert fact.source_fact == "operating system"\n    assert "learn.microsoft.com" in fact.authority_reference\n\n\ndef test_windows_26100_derives_24h2():\n    fact = derive_windows_display_version_from_operating_system(\n        "Microsoft Windows 11 Enterprise 10.0.26100.8875"\n    )\n    assert fact is not None\n    assert fact.value == "24H2"\n\n\ndef test_windows_28000_derives_26h1():\n    fact = derive_windows_display_version_from_operating_system(\n        "Microsoft Windows 11 10.0.28000.2525"\n    )\n    assert fact is not None\n    assert fact.value == "26H1"\n\n\ndef test_unknown_build_family_remains_unresolved():\n    assert derive_windows_display_version_from_operating_system(\n        "Microsoft Windows 11 Pro 10.0.99999"\n    ) is None\n\n\ndef test_non_windows_version_string_is_not_derived():\n    assert derive_windows_display_version_from_operating_system(\n        "Datto agent 4.4.11965.11965"\n    ) is None\n\n\ndef test_provider_display_version_cannot_drive_derivation():\n    assert derive_windows_display_version_from_operating_system(\n        "4.4.11965.11965"\n    ) is None\n''', encoding='utf-8')

print(f'CREATED: {module.relative_to(root)}')
print(f'CREATED: {tests.relative_to(root)}')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_derivations.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Governed Windows build-family to release derivation foundation added."
echo "Microsoft release metadata is represented as explicit versioned authority, not as LLM inference."
echo "NO RUNTIME WIRING PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED WINDOWS BUILD TO RELEASE DERIVATION =========="
