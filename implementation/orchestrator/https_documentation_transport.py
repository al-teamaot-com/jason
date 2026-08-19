from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    ProviderDocumentationSourceDefinition,
)


@dataclass(frozen=True, slots=True)
class GovernedHttpsDocumentationTransport:
    timeout_seconds: float = 10.0
    max_response_bytes: int = 5_000_000
    user_agent: str = "Jason-Governed-Documentation-Reader/1.0"

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")

    def fetch(
        self,
        *,
        source: ProviderDocumentationSourceDefinition,
    ) -> bytes:
        if source.retrieval_method not in {
            DocumentationRetrievalMethod.OPENAPI,
            DocumentationRetrievalMethod.HTTPS,
        }:
            raise PermissionError(
                "HTTPS documentation transport may only read HTTPS or OPENAPI sources"
            )

        locator = source.locator.strip()
        if not locator.startswith("https://"):
            raise PermissionError(
                "governed HTTPS documentation transport requires an HTTPS locator"
            )

        request = Request(
            locator,
            headers={
                "Accept": "application/json, application/yaml, text/yaml, */*",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise RuntimeError(
                        f"documentation source returned HTTP status {status}"
                    )

                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        announced_size = int(content_length)
                    except ValueError:
                        announced_size = None
                    if (
                        announced_size is not None
                        and announced_size > self.max_response_bytes
                    ):
                        raise ValueError(
                            "documentation source exceeds governed size limit"
                        )

                payload = response.read(self.max_response_bytes + 1)

        except HTTPError as exc:
            raise RuntimeError(
                f"documentation source returned HTTP status {exc.code}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"documentation source retrieval failed: {exc.reason}"
            ) from exc

        if len(payload) > self.max_response_bytes:
            raise ValueError(
                "documentation source exceeds governed size limit"
            )

        if not payload:
            raise ValueError("documentation source returned empty content")

        return payload
