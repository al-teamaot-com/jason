from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .provider_documentation_reader import ProviderDocumentationSourceRecord


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
    def extract_windows_display_version(
        self,
        *,
        source: ProviderDocumentationSourceRecord,
    ) -> AuthoritativeSemanticStatement:
        content = " ".join(source.content.split())
        marker = "Windows Display Version"

        index = content.find(marker)
        if index < 0:
            raise LookupError(
                "authoritative product documentation does not define Windows Display Version"
            )

        window = content[index:index + 900]

        required = (
            "friendly name",
            "Windows 10",
        )

        if not all(term.casefold() in window.casefold() for term in required):
            raise ValueError(
                "product documentation mentions Windows Display Version but "
                "does not contain sufficient authoritative semantic definition"
            )

        return AuthoritativeSemanticStatement(
            provider_id=source.provider_id,
            canonical_fact="operating system display version",
            vendor_term="Windows Display Version",
            statement=window,
            source_reference=source.source_reference,
            authoritative=True,
            semantic_mapping_approved=False,
        )
