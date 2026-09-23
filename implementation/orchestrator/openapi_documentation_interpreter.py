from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .provider_documentation_reader import (
    ProviderDocumentationCandidateFinding,
    ProviderDocumentationSourceRecord,
)
from .provider_documentation_review import ProviderDocumentationReviewTarget


_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "of",
        "for",
        "to",
        "in",
        "on",
        "with",
        "by",
        "from",
        "requested",
        "fact",
    }
)


def _terms(value: str) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in _WORD_PATTERN.findall(value)
        if token.casefold() not in _STOP_WORDS and len(token) > 1
    )


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(
            f"{key} {_flatten_text(child)}"
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_text(child) for child in value)
    return str(value)


def _relevance_score(
    *,
    requested_terms: frozenset[str],
    candidate_text: str,
) -> tuple[int, tuple[str, ...]]:
    candidate_terms = _terms(candidate_text)
    matched = tuple(sorted(requested_terms & candidate_terms))

    if not requested_terms:
        return 0, ()

    score = len(matched)

    normalized = candidate_text.casefold().replace("_", " ").replace("-", " ")
    for term in requested_terms:
        if term in normalized and term not in matched:
            score += 1

    return score, matched


@dataclass(frozen=True, slots=True)
class GovernedOpenApiDocumentationInterpreter:
    max_findings_per_fact: int = 25
    minimum_relevance_score: int = 1

    def __post_init__(self) -> None:
        if self.max_findings_per_fact < 1:
            raise ValueError("max_findings_per_fact must be positive")
        if self.minimum_relevance_score < 1:
            raise ValueError("minimum_relevance_score must be positive")

    def interpret(
        self,
        *,
        target: ProviderDocumentationReviewTarget,
        source: ProviderDocumentationSourceRecord,
    ) -> Sequence[ProviderDocumentationCandidateFinding]:
        try:
            document = json.loads(source.content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "OpenAPI documentation interpreter requires valid JSON"
            ) from exc

        if not isinstance(document, Mapping):
            raise ValueError("OpenAPI document must be a JSON object")

        findings: list[tuple[int, ProviderDocumentationCandidateFinding]] = []

        for unsupported_fact in target.unsupported_facts:
            requested_terms = _terms(unsupported_fact)

            findings.extend(
                self._operation_findings(
                    target=target,
                    source=source,
                    document=document,
                    unsupported_fact=unsupported_fact,
                    requested_terms=requested_terms,
                )
            )

            findings.extend(
                self._schema_findings(
                    target=target,
                    source=source,
                    document=document,
                    unsupported_fact=unsupported_fact,
                    requested_terms=requested_terms,
                )
            )

        deduplicated: dict[
            tuple[str, str | None, str | None, str | None],
            tuple[int, ProviderDocumentationCandidateFinding],
        ] = {}

        for score, finding in findings:
            key = (
                finding.unsupported_fact,
                finding.documented_operation,
                finding.documented_schema,
                finding.documented_field,
            )
            current = deduplicated.get(key)
            if current is None or score > current[0]:
                deduplicated[key] = (score, finding)

        ordered = sorted(
            deduplicated.values(),
            key=lambda item: (
                -item[0],
                item[1].unsupported_fact.casefold(),
                str(item[1].documented_operation or "").casefold(),
                str(item[1].documented_schema or "").casefold(),
                str(item[1].documented_field or "").casefold(),
            ),
        )

        limited: list[ProviderDocumentationCandidateFinding] = []
        per_fact_counts: dict[str, int] = {}

        for _, finding in ordered:
            count = per_fact_counts.get(finding.unsupported_fact, 0)
            if count >= self.max_findings_per_fact:
                continue
            per_fact_counts[finding.unsupported_fact] = count + 1
            limited.append(finding)

        return tuple(limited)

    def _operation_findings(
        self,
        *,
        target: ProviderDocumentationReviewTarget,
        source: ProviderDocumentationSourceRecord,
        document: Mapping[str, Any],
        unsupported_fact: str,
        requested_terms: frozenset[str],
    ) -> list[tuple[int, ProviderDocumentationCandidateFinding]]:
        results: list[
            tuple[int, ProviderDocumentationCandidateFinding]
        ] = []

        paths = document.get("paths", {})
        if not isinstance(paths, Mapping):
            return results

        for path_name, raw_path in paths.items():
            if not isinstance(raw_path, Mapping):
                continue

            for method, raw_operation in raw_path.items():
                method_name = str(method).casefold()

                if method_name not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                }:
                    continue

                if not isinstance(raw_operation, Mapping):
                    continue

                operation_id = str(
                    raw_operation.get("operationId", "")
                ).strip()

                summary = str(
                    raw_operation.get("summary", "")
                ).strip()

                description = str(
                    raw_operation.get("description", "")
                ).strip()

                candidate_text = " ".join(
                    (
                        str(path_name),
                        method_name,
                        operation_id,
                        summary,
                        description,
                        _flatten_text(
                            raw_operation.get("responses", {})
                        ),
                    )
                )

                score, matched_terms = _relevance_score(
                    requested_terms=requested_terms,
                    candidate_text=candidate_text,
                )

                if score < self.minimum_relevance_score:
                    continue

                operation = (
                    f"{method_name.upper()} {path_name}"
                )

                results.append(
                    (
                        score,
                        ProviderDocumentationCandidateFinding(
                            provider_id=target.provider_id,
                            documentation_source=target.documentation_source,
                            source_reference=(
                                f"{source.source_reference}"
                                f"#paths/{path_name}/{method_name}"
                            ),
                            unsupported_fact=unsupported_fact,
                            documented_operation=operation,
                            evidence_reference=source.source_reference,
                            relevance="possibly_relevant",
                            semantic_proof=False,
                            ambiguity_summary=(
                                "Operation documentation shares requested-fact "
                                f"terms ({', '.join(matched_terms) or 'textual similarity'}). "
                                "This establishes discoverability only, not semantic equivalence."
                            ),
                        ),
                    )
                )

        return results

    def _schema_findings(
        self,
        *,
        target: ProviderDocumentationReviewTarget,
        source: ProviderDocumentationSourceRecord,
        document: Mapping[str, Any],
        unsupported_fact: str,
        requested_terms: frozenset[str],
    ) -> list[tuple[int, ProviderDocumentationCandidateFinding]]:
        results: list[
            tuple[int, ProviderDocumentationCandidateFinding]
        ] = []

        components = document.get("components", {})
        if not isinstance(components, Mapping):
            return results

        schemas = components.get("schemas", {})
        if not isinstance(schemas, Mapping):
            return results

        for schema_name, raw_schema in schemas.items():
            if not isinstance(raw_schema, Mapping):
                continue

            schema_description = str(
                raw_schema.get("description", "")
            ).strip()

            properties = raw_schema.get("properties", {})

            schema_text = " ".join(
                (
                    str(schema_name),
                    schema_description,
                )
            )

            schema_score, schema_matches = _relevance_score(
                requested_terms=requested_terms,
                candidate_text=schema_text,
            )

            if schema_score >= self.minimum_relevance_score:
                results.append(
                    (
                        schema_score,
                        ProviderDocumentationCandidateFinding(
                            provider_id=target.provider_id,
                            documentation_source=target.documentation_source,
                            source_reference=(
                                f"{source.source_reference}"
                                f"#components/schemas/{schema_name}"
                            ),
                            unsupported_fact=unsupported_fact,
                            documented_schema=str(schema_name),
                            evidence_reference=source.source_reference,
                            relevance="semantically_ambiguous",
                            semantic_proof=False,
                            ambiguity_summary=(
                                "Schema naming or description shares requested-fact "
                                f"terms ({', '.join(schema_matches) or 'textual similarity'}). "
                                "Schema relevance does not establish field semantics."
                            ),
                        ),
                    )
                )

            if not isinstance(properties, Mapping):
                continue

            for property_name, raw_property in properties.items():
                if not isinstance(raw_property, Mapping):
                    raw_property = {}

                description = str(
                    raw_property.get("description", "")
                ).strip()

                candidate_text = " ".join(
                    (
                        str(schema_name),
                        schema_description,
                        str(property_name),
                        description,
                        _flatten_text(raw_property),
                    )
                )

                score, matched_terms = _relevance_score(
                    requested_terms=requested_terms,
                    candidate_text=candidate_text,
                )

                if score < self.minimum_relevance_score:
                    continue

                results.append(
                    (
                        score,
                        ProviderDocumentationCandidateFinding(
                            provider_id=target.provider_id,
                            documentation_source=target.documentation_source,
                            source_reference=(
                                f"{source.source_reference}"
                                f"#components/schemas/{schema_name}"
                                f"/properties/{property_name}"
                            ),
                            unsupported_fact=unsupported_fact,
                            documented_schema=str(schema_name),
                            documented_field=str(property_name),
                            evidence_reference=source.source_reference,
                            relevance="candidate_evidence",
                            semantic_proof=False,
                            ambiguity_summary=(
                                "Documented field or description shares requested-fact "
                                f"terms ({', '.join(matched_terms) or 'textual similarity'}). "
                                "Field naming alone cannot establish semantic equivalence."
                            ),
                        ),
                    )
                )

        return results
