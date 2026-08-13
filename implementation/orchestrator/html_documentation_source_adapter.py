from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from typing import Sequence

from .provider_documentation_reader import ProviderDocumentationSourceRecord
from .provider_documentation_review import ProviderDocumentationReviewTarget
from .provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    GovernedDocumentationSourceResolver,
)
from .https_documentation_transport import GovernedHttpsDocumentationTransport


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return "\n".join(self.parts)


@dataclass(frozen=True, slots=True)
class GovernedHtmlDocumentationSourceAdapter:
    resolver: GovernedDocumentationSourceResolver
    transport: GovernedHttpsDocumentationTransport
    max_document_bytes: int = 5_000_000

    def read(
        self,
        *,
        target: ProviderDocumentationReviewTarget,
    ) -> Sequence[ProviderDocumentationSourceRecord]:
        source = self.resolver.resolve(
            provider_id=target.provider_id,
            documentation_name=target.documentation_source,
            resource_authority=target.resource_authority,
        )

        if source.retrieval_method is not DocumentationRetrievalMethod.HTTPS:
            raise PermissionError(
                "HTML documentation adapter requires governed HTTPS source"
            )

        payload = self.transport.fetch(source=source)

        if len(payload) > self.max_document_bytes:
            raise ValueError("documentation source exceeds governed size limit")

        try:
            html = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("HTML documentation must be valid UTF-8") from exc

        parser = _TextExtractor()
        parser.feed(html)
        text = parser.text()

        if not text.strip():
            raise ValueError("HTML documentation yielded no readable content")

        digest = sha256(payload).hexdigest()

        return (
            ProviderDocumentationSourceRecord(
                provider_id=target.provider_id,
                documentation_source=target.documentation_source,
                source_reference=f"{source.source_id}:sha256:{digest}",
                content=text,
            ),
        )
