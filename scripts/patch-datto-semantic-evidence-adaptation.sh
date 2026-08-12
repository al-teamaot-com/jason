#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EVIDENCE ADAPTATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before Datto semantic evidence adaptation."
  printf '%s\n' "$DIRTY"
  exit 20
fi
PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "HEAD: $(git rev-parse --short HEAD)"

echo "========== SECTION 2: ADD DECLARATIVE DATTO SEMANTIC EVIDENCE MAP =========="
cat > implementation/connectors/datto_rmm/semantic_evidence.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class SemanticEvidenceField:
    canonical_fact: str
    semantic_contexts: tuple[str, ...]
    provider_keys: tuple[str, ...]


# Provider-specific declarations only. Human language and canonical fact meaning remain
# orchestrator-owned. The adapter may expose only values that actually exist in Datto
# provider evidence; it never manufactures or infers provider values.
DATTO_DEVICE_SEMANTIC_FIELDS = (
    SemanticEvidenceField(
        canonical_fact="operating system display version",
        semantic_contexts=("operating_system", "windows_release"),
        provider_keys=("displayVersion", "DisplayVersion", "display_version", "windowsDisplayVersion"),
    ),
    SemanticEvidenceField(
        canonical_fact="operating system build",
        semantic_contexts=("operating_system",),
        provider_keys=("build", "buildNumber", "osBuild", "osBuildNumber"),
    ),
    SemanticEvidenceField(
        canonical_fact="processor model",
        semantic_contexts=("processor", "hardware_inventory"),
        provider_keys=("processor", "processorModel", "cpu", "cpuModel", "processorName"),
    ),
    SemanticEvidenceField(
        canonical_fact="logical processor count",
        semantic_contexts=("processor", "hardware_inventory"),
        provider_keys=("logicalProcessors", "logicalProcessorCount", "processorCount", "threadCount"),
    ),
    SemanticEvidenceField(
        canonical_fact="total memory",
        semantic_contexts=("memory", "hardware_inventory"),
        provider_keys=("totalMemory", "physicalMemory", "totalPhysicalMemory", "ram"),
    ),
)


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


def _find_unique_provider_value(data: Any, provider_keys: tuple[str, ...]) -> Any:
    wanted = {_normalized_key(key) for key in provider_keys}
    matches: list[Any] = []
    for mapping in _walk_mappings(data):
        for raw_key, value in mapping.items():
            if _normalized_key(str(raw_key)) in wanted:
                matches.append(value)
    if len(matches) != 1:
        return None
    return matches[0]


def adapt_datto_device_semantic_evidence(data: Any) -> Any:
    """Expose Datto device evidence under provider-neutral semantic context containers.

    This is intentionally declarative and conservative. A semantic field is emitted only
    when exactly one configured Datto key exists in the provider payload. Zero or multiple
    candidates are left unresolved so the governed evidence layer can fail closed.
    """
    if not isinstance(data, Mapping):
        return data

    adapted = dict(data)
    semantic_root: dict[str, Any] = {}

    for field in DATTO_DEVICE_SEMANTIC_FIELDS:
        value = _find_unique_provider_value(data, field.provider_keys)
        if value is None:
            continue

        cursor = semantic_root
        for context in field.semantic_contexts:
            cursor = cursor.setdefault(context, {})

        semantic_key = field.canonical_fact.replace(" ", "_")
        cursor[semantic_key] = value

    if semantic_root:
        adapted["semantic_evidence"] = semantic_root
    return adapted
PY

echo "WROTE: implementation/connectors/datto_rmm/semantic_evidence.py"

echo "========== SECTION 3: APPLY ADAPTER AT DATTO DEVICE READ BOUNDARY =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/connectors/datto_rmm/connector.py')
s = p.read_text(encoding='utf-8')
import_line = 'from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence\n'
if import_line not in s:
    marker = 'from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials\n'
    if marker not in s:
        raise SystemExit('ERROR: Datto auth import anchor missing')
    s = s.replace(marker, marker + import_line, 1)

old = '            "provider_data": read_payload,\n'
new = '            "provider_data": adapt_datto_device_semantic_evidence(read_payload),\n'
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: exact device read provider_data anchor missing')

old2 = '            "provider_data": payload,\n'
new2 = '            "provider_data": adapt_datto_device_semantic_evidence(payload),\n'
if old2 in s:
    s = s.replace(old2, new2, 1)
elif new2 not in s:
    raise SystemExit('ERROR: scoped read provider_data anchor missing')

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: ADD PROVIDER ADAPTATION TESTS =========="
cat > implementation/connectors/datto_rmm/tests/test_semantic_evidence.py <<'PY'
from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence


def test_display_version_is_exposed_only_under_os_windows_release_context():
    adapted = adapt_datto_device_semantic_evidence({
        "health": {"version": "Unhealthy - Local user changes detected"},
        "operatingSystem": {"displayVersion": "24H2"},
    })
    assert adapted["semantic_evidence"]["operating_system"]["windows_release"]["operating_system_display_version"] == "24H2"
    assert adapted["health"]["version"] == "Unhealthy - Local user changes detected"


def test_ambiguous_provider_keys_fail_closed_by_omission():
    adapted = adapt_datto_device_semantic_evidence({
        "a": {"displayVersion": "23H2"},
        "b": {"DisplayVersion": "24H2"},
    })
    assert "semantic_evidence" not in adapted


def test_processor_model_and_count_remain_distinct_semantic_fields():
    adapted = adapt_datto_device_semantic_evidence({
        "hardware": {
            "processorModel": "Intel Core i7-12700",
            "logicalProcessors": 20,
        }
    })
    processor = adapted["semantic_evidence"]["processor"]["hardware_inventory"]
    assert processor["processor_model"] == "Intel Core i7-12700"
    assert processor["logical_processor_count"] == 20
PY

echo "WROTE: implementation/connectors/datto_rmm/tests/test_semantic_evidence.py"

echo "========== SECTION 5: VALIDATE =========="
git diff --check
$PY -m py_compile \
  implementation/connectors/datto_rmm/semantic_evidence.py \
  implementation/connectors/datto_rmm/connector.py
$PY -m pytest -q \
  implementation/connectors/datto_rmm/tests/test_semantic_evidence.py \
  implementation/connectors/datto_rmm/tests/test_connector.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Datto semantic evidence adaptation validated."
echo "Provider-native device evidence can now be exposed through semantic context containers without changing human intent semantics."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END DATTO SEMANTIC EVIDENCE ADAPTATION =========="
