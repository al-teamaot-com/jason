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
    SemanticEvidenceField(
        canonical_fact="endpoint last seen",
        semantic_contexts=("endpoint", "presence"),
        provider_keys=("lastSeen",),
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

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    # Provider payloads may repeat the same authoritative value under multiple
    # aliases or inventory sections. Equivalent duplicates are not ambiguity.
    # Conflicting values remain unresolved and fail closed.
    first = matches[0]
    if all(value == first for value in matches[1:]):
        return first
    return None


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
