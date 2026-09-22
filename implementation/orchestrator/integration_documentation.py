"""Live provider documentation available to Jason reasoning.

The provider's published URL remains authoritative.  A small in-memory cache
avoids repeatedly downloading the same document during normal reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from time import monotonic
from typing import Callable
from urllib.request import Request, urlopen

from .integration_broker import IntegrationBroker


_MAX_DOCUMENT_CHARS = 250_000


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag.casefold() in {
            "script",
            "style",
            "noscript",
        }:
            self._hidden_depth += 1

    def handle_endtag(self, tag) -> None:
        if (
            tag.casefold()
            in {
                "script",
                "style",
                "noscript",
            }
            and self._hidden_depth
        ):
            self._hidden_depth -= 1

    def handle_data(self, data) -> None:
        if self._hidden_depth:
            return

        clean = " ".join(
            str(data).split()
        )

        if clean:
            self.parts.append(clean)


@dataclass(frozen=True, slots=True)
class IntegrationDocumentation:
    integration_id: str
    source_url: str
    document_type: str
    content: str


@dataclass(slots=True)
class LiveIntegrationDocumentationReader:
    broker: IntegrationBroker
    max_age_seconds: int = 900
    opener: Callable = urlopen
    _cache: dict[
        str,
        tuple[float, IntegrationDocumentation],
    ] = field(
        default_factory=dict,
    )

    def read(
        self,
        integration_id: str,
        *,
        force_refresh: bool = False,
    ) -> IntegrationDocumentation:
        clean_id = str(
            integration_id
        ).strip()

        if not clean_id:
            raise ValueError(
                "integration_id is required"
            )

        now = monotonic()
        cached = self._cache.get(
            clean_id
        )

        if (
            not force_refresh
            and cached is not None
            and now - cached[0]
            < self.max_age_seconds
        ):
            return cached[1]

        view = next(
            (
                item
                for item
                in self.broker.list_integrations()
                if item.integration_id
                == clean_id
            ),
            None,
        )

        if view is None:
            raise LookupError(
                "integration is not registered: "
                + clean_id
            )

        metadata = dict(
            view.manifest.metadata
        )

        source_url = str(
            metadata.get(
                "documentation_url",
                "",
            )
        ).strip()

        document_type = str(
            metadata.get(
                "documentation_type",
                "",
            )
        ).strip().casefold()

        if not source_url:
            raise LookupError(
                "integration has no documentation URL: "
                + clean_id
            )

        if document_type not in {
            "html",
            "openapi",
            "json",
        }:
            raise ValueError(
                "unsupported integration documentation type"
            )

        request = Request(
            source_url,
            headers={
                "Accept": (
                    "application/json"
                    if document_type
                    in {
                        "openapi",
                        "json",
                    }
                    else "text/html"
                ),
                "User-Agent": (
                    "Jason-Integration-Documentation/1.0"
                ),
            },
            method="GET",
        )

        with self.opener(
            request,
            timeout=30,
        ) as response:
            raw = response.read()

        text = raw.decode(
            "utf-8",
            errors="replace",
        )

        if document_type == "html":
            parser = _VisibleTextParser()
            parser.feed(text)

            text = "\n".join(
                parser.parts
            )

        text = text.strip()

        if not text:
            raise ValueError(
                "integration documentation was empty"
            )

        if len(text) > _MAX_DOCUMENT_CHARS:
            text = text[
                :_MAX_DOCUMENT_CHARS
            ]

        document = IntegrationDocumentation(
            integration_id=clean_id,
            source_url=source_url,
            document_type=document_type,
            content=text,
        )

        self._cache[
            clean_id
        ] = (
            now,
            document,
        )

        return document
