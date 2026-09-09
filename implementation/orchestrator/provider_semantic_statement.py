from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .provider_documentation_reader import ProviderDocumentationSourceRecord


@dataclass(frozen=True, slots=True)
class SemanticStatementQuery:
    canonical_fact: str
    vendor_term: str
    required_phrases: tuple[str, ...] = ()
    context_window_chars: int = 1200

    def __post_init__(self) -> None:
        if not self.canonical_fact.strip():
            raise ValueError("canonical_fact is required")
        if not self.vendor_term.strip():
            raise ValueError("vendor_term is required")
        if self.context_window_chars < 128 or self.context_window_chars > 10000:
            raise ValueError("context_window_chars is outside governed bounds")


@dataclass(frozen=True, slots=True)
class AuthoritativeSemanticStatement:
    provider_id: str
    canonical_fact: str
    vendor_term: str
    statement: str
    source_reference: str
    authoritative: bool = True
    semantic_mapping_approved: bool = False

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "canonical_fact": self.canonical_fact,
            "vendor_term": self.vendor_term,
            "statement": self.statement,
            "source_reference": self.source_reference,
            "authoritative": self.authoritative,
            "semantic_mapping_approved": False,
        }


@dataclass(frozen=True, slots=True)
class GovernedSemanticStatementExtractor:
    def extract(
        self,
        *,
        source: ProviderDocumentationSourceRecord,
        query: SemanticStatementQuery,
    ) -> AuthoritativeSemanticStatement:
        content = " ".join(source.content.split())

        index = content.casefold().find(query.vendor_term.casefold())
        if index < 0:
            raise LookupError(
                "authoritative product documentation does not contain "
                "the governed vendor semantic term"
            )

        window = content[index:index + query.context_window_chars]

        missing = tuple(
            phrase
            for phrase in query.required_phrases
            if phrase.casefold() not in window.casefold()
        )

        if missing:
            raise ValueError(
                "authoritative documentation contains the vendor term but "
                "does not satisfy the governed semantic evidence query; "
                f"missing required phrase(s): {', '.join(missing)}"
            )

        return AuthoritativeSemanticStatement(
            provider_id=source.provider_id,
            canonical_fact=query.canonical_fact,
            vendor_term=query.vendor_term,
            statement=window,
            source_reference=source.source_reference,
            authoritative=True,
            semantic_mapping_approved=False,
        )
