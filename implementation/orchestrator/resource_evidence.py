from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .contracts import OrchestrationResult, OrchestrationStatus
from .canonical_fact_vocabulary import CanonicalFactVocabulary
from .evidence_sanitization import sanitize_evidence_tree
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
class SemanticMappingEvidenceProjector(Protocol):
    def project(
        self,
        *,
        provider_id: str,
        capability_name: str,
        data: Any,
        requested_facts: tuple[str, ...],
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class GovernedResourceEvidenceInterpreter:
    reasoner: StructuredResourceEvidenceReasoner
    fact_vocabulary: CanonicalFactVocabulary | None = None
    semantic_mapping_projector: SemanticMappingEvidenceProjector | None = None

    def interpret(
        self,
        *,
        result: OrchestrationResult,
        requested_facts: tuple[str, ...],
        evidence_contexts: Mapping[str, tuple[str, ...]] | None = None,
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

        if self.semantic_mapping_projector is not None:
            data = self.semantic_mapping_projector.project(
                provider_id=result.provider_id,
                capability_name=result.capability_name,
                data=data,
                requested_facts=requested_facts,
            )

        # Evidence exposed to language reasoning or response assembly must be
        # deterministically sanitized first. The provider remains the source of
        # truth; sanitization only removes credential-bearing values.
        data = sanitize_evidence_tree(data)

        direct_facts = _deterministic_direct_facts(
            data=data,
            requested_facts=requested_facts,
        )
        verified_by_fact: dict[str, VerifiedResourceFact] = {}
        for fact in direct_facts:
            if self.fact_vocabulary is not None:
                definition = self.fact_vocabulary.resolve(fact.requested_fact)
                if definition is not None and not _value_matches_expected_shape(
                    fact.value,
                    definition.expected_shape,
                ):
                    continue
            verified_by_fact[fact.requested_fact] = fact
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

                # Semantic context remains useful knowledge for planning and
                # explanation, but provider field names are not required to
                # repeat Jason's ontology terminology. The bounded reasoner
                # selects only an allowed structural path; Jason then
                # deterministically dereferences the sanitized provider value.
                if self.fact_vocabulary is not None:
                    definition = self.fact_vocabulary.resolve(requested_fact)
                    if definition is not None and not _value_matches_expected_shape(
                        actual,
                        definition.expected_shape,
                    ):
                        raise LookupError(
                            f"provider evidence has wrong shape for {requested_fact}: "
                            f"expected {definition.expected_shape}"
                        )
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

        # Provider-scoped read capabilities return canonical evidence beneath
        # provider_data. Treat direct fields at this boundary as structurally
        # authoritative just like direct top-level fields. This lets a request
        # for "software", "alerts", "bios", etc. resolve to the complete
        # provider collection/object rather than allowing language reasoning
        # to select an arbitrary nested scalar.
        provider_data = data.get("provider_data")
        if isinstance(provider_data, Mapping):
            locations.append(("/provider_data", provider_data))

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

        # Provider adapters may expose deterministic canonical facts beneath
        # provider_data/semantic_evidence. Those paths are deliberately trusted
        # only as locations, never as asserted values: Jason still dereferences
        # the actual provider-derived value and applies semantic-context and
        # expected-shape validation afterward. This avoids asking a language
        # reasoner to rediscover a provider mapping that the adapter already
        # declared explicitly.
        if isinstance(data, Mapping):
            provider_data = data.get("provider_data")
            if isinstance(provider_data, Mapping):
                semantic_root = provider_data.get("semantic_evidence")
                if isinstance(semantic_root, Mapping):

                    def walk_semantic(value: Any, pointer: str) -> None:
                        if not isinstance(value, Mapping):
                            return
                        for raw_key, child in value.items():
                            key = str(raw_key)
                            child_pointer = f"{pointer}/{_escape_json_pointer_segment(key)}"
                            if _normalized_field_name(key) == wanted:
                                candidates.append((child_pointer, child))
                            walk_semantic(child, child_pointer)

                    walk_semantic(
                        semantic_root,
                        "/provider_data/semantic_evidence",
                    )
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


def _normalized_semantic_tokens(value: str) -> set[str]:
    return {
        token
        for token in "".join(
            character if character.isalnum() else " "
            for character in value.casefold()
        ).split()
        if token
    }


def _evidence_matches_contexts(*, pointer: str, contexts: tuple[str, ...]) -> bool:
    """Require evidence location to carry provider-neutral semantic context.

    Contexts protect arbitrary provider paths selected through bounded reasoning.

    Evidence beneath provider_data/semantic_evidence is different: that location exists
    only because a governed provider adapter or approved semantic mapping deliberately
    projected a provider-derived value into a canonical semantic location. Requiring the
    canonical path to repeat every lexical context from the human request can therefore
    reject correctly governed evidence (for example, a human saying "Windows" when the
    canonical fact is "operating system display version").

    The value is still dereferenced from provider evidence and still passes canonical
    expected-shape validation; this exception grants no authority to an AI reasoner and
    does not permit arbitrary provider paths.
    """
    if pointer.startswith("/provider_data/semantic_evidence/"):
        return True

    if not contexts:
        return True
    pointer_tokens = _normalized_semantic_tokens(pointer)
    if not pointer_tokens:
        return False
    for context in contexts:
        context_tokens = _normalized_semantic_tokens(context)
        if not context_tokens:
            continue
        if pointer_tokens.isdisjoint(context_tokens):
            return False
    return True


def _value_matches_expected_shape(value: Any, expected_shape: str) -> bool:
    """Validate provider evidence against the provider-neutral fact contract."""
    if expected_shape == "descriptive_string":
        return isinstance(value, str) and bool(value.strip()) and not value.strip().isdigit()
    if expected_shape == "integer_count":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if expected_shape == "capacity":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value >= 0
        if isinstance(value, str):
            text = value.strip().casefold()
            return bool(text) and any(
                unit in text for unit in ("kb", "mb", "gb", "tb", "bytes", "byte")
            )
        return False
    if expected_shape == "collection":
        return isinstance(value, (list, tuple))
    return True


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
        raw_contexts = intent.arguments.get("evidence_contexts")
        evidence_contexts: dict[str, tuple[str, ...]] | None = None
        if isinstance(raw_contexts, Mapping):
            evidence_contexts = {}
            for raw_fact, raw_values in raw_contexts.items():
                if not isinstance(raw_values, (list, tuple)):
                    raise ValueError("conversation evidence contexts must be a list/tuple")
                evidence_contexts[str(raw_fact).strip()] = tuple(
                    str(item).strip() for item in raw_values if str(item).strip()
                )

        try:
            facts = self.interpreter.interpret(
                result=result,
                requested_facts=requested_facts,
                evidence_contexts=evidence_contexts,
            )
        except LookupError:
            # A successful governed provider read can legitimately lack evidence for
            # a requested semantic fact. That is not an unsafe action failure. Preserve
            # fail-closed semantics while telling the human exactly what is unavailable.
            rendered_facts = ", ".join(requested_facts)
            return (
                f"{subject} — {rendered_facts}: unavailable from the current governed "
                f"provider evidence. Source: {source}."
            )

        collection_facts = tuple(
            fact
            for fact in facts
            if isinstance(fact.value, (list, tuple))
        )

        if collection_facts:
            # A human asking about a resource collection normally needs the
            # existence/count and a concise operational summary, not the raw
            # provider object. Complete evidence remains in the governed
            # orchestration result and can be requested explicitly later.
            primary = collection_facts[0]
            return _render_collection_response(
                subject=subject,
                source=source,
                fact=primary,
                result_intent=str(
                    intent.arguments.get(
                        "result_intent",
                        "summary",
                    )
                ).strip(),
                completeness_requirement=str(
                    intent.arguments.get(
                        "completeness_requirement",
                        "sufficient",
                    )
                ).strip(),
            )

        if len(facts) == 1:
            fact = facts[0]
            return (
                f"{subject} — {fact.requested_fact}: "
                f"{_display_value(fact.value)}. Source: {source}."
            )

        rendered = "; ".join(
            f"{fact.requested_fact}: {_display_value(fact.value)}"
            for fact in facts
        )
        return f"{subject} — {rendered}. Source: {source}."


def _render_collection_response(
    *,
    subject: str,
    source: str,
    fact: VerifiedResourceFact,
    result_intent: str = "summary",
    completeness_requirement: str = "sufficient",
) -> str:
    """Render provider evidence according to the governed result contract."""

    values = tuple(fact.value)
    label = _human_collection_label(
        fact.requested_fact,
        len(values),
    )

    if not values:
        return f"{subject} — no {label} found. Source: {source}."

    if result_intent == "count":
        return (
            f"{subject} — {len(values)} {label} found. "
            f"Source: {source}."
        )

    if (
        result_intent == "enumerate"
        and completeness_requirement == "complete"
    ):
        # A complete inline enumeration remains bounded for transport safety.
        # If a collection is too large for one message, do not pretend the
        # partial rendering satisfied a complete request.
        max_inline_items = 100

        if len(values) > max_inline_items:
            return (
                f"{subject} — {len(values)} {label} found, but the complete "
                f"collection exceeds the {max_inline_items}-item inline "
                f"response limit. Source: {source}."
            )

        summaries = tuple(
            summary
            for item in values
            if (summary := _summarize_collection_item(item))
        )

        if len(summaries) != len(values):
            raise LookupError(
                "complete collection rendering could not summarize every item"
            )

        heading = f"{subject} — {len(values)} {label} found:"
        body = "\n".join(
            f"- {summary}"
            for summary in summaries
        )
        return f"{heading}\n{body}\nSource: {source}."

    heading = f"{subject} — {len(values)} {label} found."

    summaries = tuple(
        summary
        for item in values[:5]
        if (summary := _summarize_collection_item(item))
    )

    if not summaries:
        return f"{heading} Source: {source}."

    detail = " | ".join(summaries)

    remaining = len(values) - len(summaries)
    if remaining > 0:
        detail += f" | +{remaining} more"

    return f"{heading} {detail}. Source: {source}."


def _human_collection_label(requested_fact: str, count: int) -> str:
    label = requested_fact.strip().replace("_", " ")

    for prefix in ("open ", "resolved ", "installed "):
        if label.casefold().startswith(prefix):
            label = label[len(prefix):]
            break

    if count == 1 and label.endswith("s") and len(label) > 1:
        label = label[:-1]

    return label or "items"


def _summarize_collection_item(value: Any) -> str:
    """Return a bounded operational summary without dumping provider JSON."""

    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        return _bounded_scalar(value)

    if not isinstance(value, Mapping):
        return ""

    parts: list[str] = []

    for key in (
        "priority",
        "severity",
        "status",
        "name",
        "displayName",
        "title",
        "softwareName",
        "productName",
        "siteName",
        "deviceName",
        "hostname",
        "version",
    ):
        scalar = _bounded_scalar(value.get(key))
        if scalar and scalar not in parts:
            parts.append(scalar)
        if len(parts) >= 2:
            break

    descriptive = _find_descriptive_scalar(value)
    if descriptive and descriptive not in parts:
        parts.append(descriptive)

    if not parts:
        return "record"

    return " — ".join(parts[:3])[:420]


def _find_descriptive_scalar(value: Mapping[str, Any]) -> str:
    preferred = (
        "summary",
        "message",
        "description",
        "reason",
        "details",
        "Status",
    )

    for key in preferred:
        scalar = _bounded_scalar(value.get(key))
        if scalar:
            return scalar

    for outer_key in (
        "alertContext",
        "samples",
        "context",
        "info",
        "metadata",
        "alertSourceInfo",
    ):
        nested = value.get(outer_key)
        if not isinstance(nested, Mapping):
            continue

        for key in preferred:
            scalar = _bounded_scalar(nested.get(key))
            if scalar:
                return scalar

        samples = nested.get("samples")
        if isinstance(samples, Mapping):
            for key in preferred:
                scalar = _bounded_scalar(samples.get(key))
                if scalar:
                    return scalar

    return ""


def _bounded_scalar(value: Any) -> str:
    if not isinstance(value, (str, int, float, bool)):
        return ""

    rendered = str(value).strip()
    if not rendered:
        return ""

    rendered = " ".join(rendered.split())
    return rendered[:280]


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
