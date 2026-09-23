from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .provider_documentation_review import ProviderDocumentationReviewTarget


_ALLOWED_RELEVANCE = frozenset(
    {
        "irrelevant",
        "possibly_relevant",
        "semantically_ambiguous",
        "candidate_evidence",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderDocumentationSourceRecord:
    provider_id: str
    documentation_source: str
    source_reference: str
    content: str

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if not self.documentation_source.strip():
            raise ValueError("documentation_source is required")
        if not self.source_reference.strip():
            raise ValueError("source_reference is required")
        if not self.content.strip():
            raise ValueError("documentation content is required")


@dataclass(frozen=True, slots=True)
class ProviderDocumentationCandidateFinding:
    provider_id: str
    documentation_source: str
    source_reference: str
    unsupported_fact: str
    documented_operation: str | None = None
    documented_field: str | None = None
    documented_schema: str | None = None
    evidence_reference: str | None = None
    relevance: str = "possibly_relevant"
    semantic_proof: bool = False
    ambiguity_summary: str | None = None

    def __post_init__(self) -> None:
        if self.relevance not in _ALLOWED_RELEVANCE:
            raise ValueError("documentation finding relevance is invalid")

        if self.semantic_proof:
            raise PermissionError(
                "documentation reader findings cannot establish semantic proof"
            )

        if not self.unsupported_fact.strip():
            raise ValueError("unsupported_fact is required")

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "documentation_source": self.documentation_source,
            "source_reference": self.source_reference,
            "unsupported_fact": self.unsupported_fact,
            "documented_operation": self.documented_operation,
            "documented_field": self.documented_field,
            "documented_schema": self.documented_schema,
            "evidence_reference": self.evidence_reference,
            "relevance": self.relevance,
            "semantic_proof": False,
            "ambiguity_summary": self.ambiguity_summary,
        }


@dataclass(frozen=True, slots=True)
class ProviderDocumentationReadResult:
    target: ProviderDocumentationReviewTarget
    findings: tuple[ProviderDocumentationCandidateFinding, ...]
    review_only: bool = True
    governance_owner: str = "technology-steward"
    interpretation_rule: str = (
        "Documentation similarity, field naming, schema naming, or operation naming "
        "does not establish semantic equivalence. Findings are candidate evidence only "
        "until separately validated through governed semantic/evidence review."
    )

    def as_context(self) -> Mapping[str, object]:
        return {
            "target": self.target.as_context(),
            "findings": tuple(item.as_context() for item in self.findings),
            "review_only": self.review_only,
            "governance_owner": self.governance_owner,
            "interpretation_rule": self.interpretation_rule,
        }


class ProviderDocumentationSourceReader(Protocol):
    def read(
        self,
        *,
        target: ProviderDocumentationReviewTarget,
    ) -> Sequence[ProviderDocumentationSourceRecord]: ...


class ProviderDocumentationInterpreter(Protocol):
    def interpret(
        self,
        *,
        target: ProviderDocumentationReviewTarget,
        source: ProviderDocumentationSourceRecord,
    ) -> Sequence[ProviderDocumentationCandidateFinding]: ...


@dataclass(frozen=True, slots=True)
class GovernedProviderDocumentationReader:
    source_reader: ProviderDocumentationSourceReader
    interpreter: ProviderDocumentationInterpreter

    def read(
        self,
        *,
        target: ProviderDocumentationReviewTarget,
    ) -> ProviderDocumentationReadResult:
        records = tuple(self.source_reader.read(target=target))

        findings: list[ProviderDocumentationCandidateFinding] = []

        for source in records:
            if source.provider_id != target.provider_id:
                raise PermissionError(
                    "documentation source provider does not match governed review target"
                )

            if source.documentation_source != target.documentation_source:
                raise PermissionError(
                    "documentation source does not match governed review target"
                )

            interpreted = tuple(
                self.interpreter.interpret(
                    target=target,
                    source=source,
                )
            )

            for finding in interpreted:
                if finding.provider_id != target.provider_id:
                    raise PermissionError(
                        "documentation finding provider does not match governed target"
                    )

                if finding.documentation_source != target.documentation_source:
                    raise PermissionError(
                        "documentation finding source does not match governed target"
                    )

                if finding.unsupported_fact not in target.unsupported_facts:
                    raise PermissionError(
                        "documentation finding addresses a fact outside governed review target"
                    )

                if finding.semantic_proof:
                    raise PermissionError(
                        "documentation reader cannot establish semantic proof"
                    )

                findings.append(finding)

        findings.sort(
            key=lambda item: (
                item.unsupported_fact.casefold(),
                str(item.documented_operation or "").casefold(),
                str(item.documented_field or "").casefold(),
                item.source_reference.casefold(),
            )
        )

        return ProviderDocumentationReadResult(
            target=target,
            findings=tuple(findings),
        )
