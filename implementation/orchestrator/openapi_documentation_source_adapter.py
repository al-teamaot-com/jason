from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Protocol, Sequence

from .provider_documentation_reader import ProviderDocumentationSourceRecord
from .provider_documentation_review import ProviderDocumentationReviewTarget
from .provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    GovernedDocumentationSourceResolver,
    ProviderDocumentationSourceDefinition,
)


class DocumentationContentTransport(Protocol):
    def fetch(
        self,
        *,
        source: ProviderDocumentationSourceDefinition,
    ) -> bytes: ...


@dataclass(frozen=True, slots=True)
class GovernedOpenApiDocumentationSourceAdapter:
    resolver: GovernedDocumentationSourceResolver
    transport: DocumentationContentTransport
    max_document_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        if self.max_document_bytes < 1:
            raise ValueError("max_document_bytes must be positive")

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

        if source.retrieval_method is not DocumentationRetrievalMethod.OPENAPI:
            raise PermissionError(
                "governed OpenAPI adapter may only read OPENAPI documentation sources"
            )

        payload = self.transport.fetch(source=source)

        if not isinstance(payload, bytes):
            raise TypeError("documentation transport must return bytes")

        if not payload:
            raise ValueError("documentation source returned empty content")

        if len(payload) > self.max_document_bytes:
            raise ValueError("documentation source exceeds governed size limit")

        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                "OpenAPI documentation source must be valid UTF-8"
            ) from exc

        digest = sha256(payload).hexdigest()

        return (
            ProviderDocumentationSourceRecord(
                provider_id=target.provider_id,
                documentation_source=target.documentation_source,
                source_reference=f"{source.source_id}:sha256:{digest}",
                content=text,
            ),
        )


@dataclass(frozen=True, slots=True)
class StaticDocumentationContentTransport:
    documents: Mapping[str, bytes]

    def fetch(
        self,
        *,
        source: ProviderDocumentationSourceDefinition,
    ) -> bytes:
        try:
            return self.documents[source.locator]
        except KeyError as exc:
            raise LookupError(
                "documentation content is unavailable for governed locator"
            ) from exc
