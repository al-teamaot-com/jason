from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .contracts import OrchestrationResult, OrchestrationStatus
from .teams_conversation_flow import ConversationIntent


class StructuredResourceEvidenceReasoner(Protocol):
    """Identify evidence paths for requested facts without authority to assert values.

    The reasoner may inspect the provider result and say where a requested fact appears.
    Jason deterministically dereferences that path and uses the actual provider value;
    a model-supplied value is never trusted as evidence.
    """

    def locate(
        self,
        *,
        requested_facts: tuple[str, ...],
        data: Any,
    ) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class VerifiedResourceFact:
    requested_fact: str
    value: Any
    json_pointer: str


@dataclass(frozen=True, slots=True)
class GovernedResourceEvidenceInterpreter:
    reasoner: StructuredResourceEvidenceReasoner

    def interpret(
        self,
        *,
        result: OrchestrationResult,
        requested_facts: tuple[str, ...],
    ) -> tuple[VerifiedResourceFact, ...]:
        if result.status is not OrchestrationStatus.SUCCEEDED:
            raise LookupError("resource evidence is unavailable because orchestration did not succeed")
        if not requested_facts or not all(item.strip() for item in requested_facts):
            raise ValueError("requested_facts must be non-empty")

        provider = str(result.output.get("provider", "")).strip()
        if not provider or not result.provider_id or provider != result.provider_id:
            raise RuntimeError("resource result provider provenance is missing or inconsistent")
        if "data" not in result.output:
            raise RuntimeError("resource result does not contain provider data")
        data = result.output["data"]

        verified_by_fact = {
            fact.requested_fact: fact
            for fact in _deterministic_direct_facts(
                data=data,
                requested_facts=requested_facts,
            )
        }
        unresolved = tuple(
            fact for fact in requested_facts if fact not in verified_by_fact
        )

        if unresolved:
            proposals = tuple(
                self.reasoner.locate(
                    requested_facts=unresolved,
                    data=data,
                )
            )
            if not proposals:
                raise LookupError("requested facts were not located in governed provider evidence")

            allowed_facts = set(unresolved)
            seen: set[str] = set()
            for proposal in proposals:
                if not isinstance(proposal, Mapping):
                    raise ValueError("resource evidence proposal must be an object")
                requested_fact = str(proposal.get("requested_fact", "")).strip()
                pointer = str(proposal.get("json_pointer", "")).strip()
                if requested_fact not in allowed_facts:
                    raise PermissionError("evidence reasoner attempted to assert an unrequested fact")
                if requested_fact in seen:
                    raise ValueError("evidence reasoner returned duplicate requested facts")
                if not pointer.startswith("/"):
                    raise ValueError("resource evidence must use an absolute JSON Pointer")

                actual = _resolve_json_pointer(data, pointer)
                verified_by_fact[requested_fact] = VerifiedResourceFact(
                    requested_fact=requested_fact,
                    value=actual,
                    json_pointer=pointer,
                )
                seen.add(requested_fact)

            missing = tuple(fact for fact in unresolved if fact not in seen)
            if missing:
                raise LookupError(
                    "governed provider evidence did not support all requested facts: "
                    + ", ".join(missing)
                )

        return tuple(verified_by_fact[fact] for fact in requested_facts)


def _resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve RFC 6901-style JSON Pointer against provider evidence."""

    current = document
    for raw_segment in pointer.split("/")[1:]:
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if segment not in current:
                raise LookupError(f"resource evidence pointer does not exist: {pointer}")
            current = current[segment]
            continue
        if isinstance(current, (list, tuple)):
            try:
                index = int(segment)
            except ValueError as error:
                raise LookupError(f"resource evidence pointer has invalid list index: {pointer}") from error
            if index < 0 or index >= len(current):
                raise LookupError(f"resource evidence pointer is outside the result: {pointer}")
            current = current[index]
            continue
        raise LookupError(f"resource evidence pointer traverses a scalar value: {pointer}")
    return current


def _deterministic_direct_facts(
    *,
    data: Any,
    requested_facts: tuple[str, ...],
) -> tuple[VerifiedResourceFact, ...]:
    """Resolve canonical direct fields without using language reasoning.

    This deliberately considers only structurally authoritative locations: the provider
    data object itself and, for discovery results, a single canonical resource match.
    It does not recursively search arbitrary provider payloads or infer aliases. A fact
    is resolved here only when its normalized label maps to exactly one direct field.
    Semantic or provider-specific facts continue through the bounded evidence reasoner.
    """

    locations: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(data, Mapping):
        locations.append(("", data))
        raw_matches = data.get("resource_matches")
        if (
            isinstance(raw_matches, (list, tuple))
            and len(raw_matches) == 1
            and isinstance(raw_matches[0], Mapping)
        ):
            locations.append(("/resource_matches/0", raw_matches[0]))

    verified: list[VerifiedResourceFact] = []
    for requested_fact in requested_facts:
        wanted = _normalized_field_name(requested_fact)
        candidates: list[tuple[str, Any]] = []
        for prefix, mapping in locations:
            for raw_key, value in mapping.items():
                key = str(raw_key)
                if _normalized_field_name(key) != wanted:
                    continue
                pointer = f"{prefix}/{_escape_json_pointer_segment(key)}"
                candidates.append((pointer, value))

        if len(candidates) != 1:
            continue
        pointer, value = candidates[0]
        verified.append(
            VerifiedResourceFact(
                requested_fact=requested_fact,
                value=value,
                json_pointer=pointer,
            )
        )
    return tuple(verified)


def _normalized_field_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _escape_json_pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True, slots=True)
class GovernedTeamsResourceResponseRenderer:
    """Render only facts deterministically verified against governed provider evidence.

    Discovery selectors never become durable resource identity merely because a
    provider returned a first result. Endpoint and System Registry name discovery
    expose canonical resource_matches. Ambiguous identity-like searches fail closed;
    broad System Registry filters may intentionally return a governed result set.
    """

    interpreter: GovernedResourceEvidenceInterpreter

    def render(self, result: OrchestrationResult, intent: ConversationIntent) -> str:
        source = result.provider_id or "governed provider"
        subject = _resource_subject(intent.arguments)

        if intent.capability_name == "endpoint.device.search":
            matches = _canonical_resource_matches(result)
            if not matches:
                return f"{subject} — no matching managed endpoint was found. Source: {source}."
            if len(matches) > 1:
                return (
                    f"{subject} is ambiguous: {len(matches)} managed endpoints matched. "
                    "Please specify the site/client or a durable resource identifier. "
                    f"No device was selected. Source: {source}."
                )
            resource_id = str(matches[0].get("resource_id", "")).strip()
            if not resource_id:
                raise LookupError(
                    "endpoint discovery produced one candidate without a durable resource identity"
                )

        if intent.capability_name == "system.registry.search":
            matches = _canonical_resource_matches(result)
            if not matches:
                return f"{subject} — no matching System Registry entity was found. Source: {source}."
            identity_like = any(
                str(intent.arguments.get(key, "")).strip()
                for key in ("name", "registry_id", "query")
            )
            if identity_like and len(matches) > 1:
                return (
                    f"{subject} is ambiguous: {len(matches)} System Registry entities matched. "
                    "Please specify the durable registry resource_id or a more exact name. "
                    f"No entity was selected. Source: {source}."
                )
            if len(matches) == 1:
                resource_id = str(matches[0].get("resource_id", "")).strip()
                if not resource_id:
                    raise LookupError(
                        "System Registry discovery produced one candidate without durable resource identity"
                    )

        raw_requested_facts = intent.arguments.get("requested_facts", ())
        if not isinstance(raw_requested_facts, (list, tuple)):
            raise ValueError("conversation resource intent is missing requested_facts")
        requested_facts = tuple(str(item).strip() for item in raw_requested_facts)
        facts = self.interpreter.interpret(
            result=result,
            requested_facts=requested_facts,
        )

        if len(facts) == 1:
            fact = facts[0]
            return f"{subject} — {fact.requested_fact}: {_display_value(fact.value)}. Source: {source}."

        rendered = "; ".join(
            f"{fact.requested_fact}: {_display_value(fact.value)}" for fact in facts
        )
        return f"{subject} — {rendered}. Source: {source}."


def _canonical_resource_matches(result: OrchestrationResult) -> tuple[Mapping[str, Any], ...]:
    if result.status is not OrchestrationStatus.SUCCEEDED:
        raise LookupError("resource discovery is unavailable because orchestration did not succeed")
    data = result.output.get("data")
    if not isinstance(data, Mapping):
        raise RuntimeError("resource discovery result must contain canonical provider data")
    raw_matches = data.get("resource_matches")
    if not isinstance(raw_matches, (list, tuple)):
        raise RuntimeError("resource discovery result is missing canonical resource_matches")
    if not all(isinstance(item, Mapping) for item in raw_matches):
        raise RuntimeError("resource discovery returned an invalid canonical resource match")
    return tuple(raw_matches)


def _resource_subject(arguments: Mapping[str, Any]) -> str:
    for key in (
        "hostname",
        "name",
        "registry_id",
        "resource_id",
        "serial_number",
        "from",
        "query",
    ):
        value = arguments.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "Requested resource"


def _display_value(value: Any) -> str:
    if value is None:
        return "not reported"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(", ", ": "))
    raise ValueError("resource evidence fact must resolve to JSON-compatible evidence")
