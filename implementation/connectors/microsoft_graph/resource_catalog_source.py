"""Governed Microsoft Graph structural catalog source.

The source fetches the provider-published Graph CSDL document from the fixed governed
Graph metadata endpoint and converts it to Jason's bounded resource catalog.  Tenant
application identity is used only to prove a configured client boundary and authenticate
the provider request.  Entity-set and field names are learned from Microsoft metadata;
none are enumerated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable, Protocol

from connectors.core.contracts import ConnectorAuthorizationError

from .platform import MicrosoftCloudRequest, build_governed_request
from .resource_metadata import MicrosoftGraphResourceCatalog, discover_graph_resources
from .service_catalog import MicrosoftOperationMode, MicrosoftService


class MicrosoftGraphMetadataTextTransport(Protocol):
    def request_text(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float = 30.0,
    ) -> str: ...


class MicrosoftGraphClientApplicationTokenProvider(Protocol):
    def acquire_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class _CachedCatalog:
    catalog: MicrosoftGraphResourceCatalog
    expires_at: float


@dataclass(slots=True)
class MicrosoftGraphMetadataCatalogSource:
    """Resolve a bounded provider schema for an already-governed client boundary."""

    tokens: MicrosoftGraphClientApplicationTokenProvider
    transport: MicrosoftGraphMetadataTextTransport
    permission_profile_name: str = "directory-read"
    timeout_seconds: float = 20.0
    cache_ttl_seconds: int = 3600
    clock: Callable[[], float] = monotonic
    _cache: dict[str, _CachedCatalog] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.permission_profile_name.strip():
            raise ValueError("Microsoft metadata permission profile is required")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("Microsoft metadata timeout must be between 0 and 60 seconds")
        if self.cache_ttl_seconds < 60 or self.cache_ttl_seconds > 86400:
            raise ValueError("Microsoft metadata cache ttl must be between 60 and 86400 seconds")

    def catalog_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> MicrosoftGraphResourceCatalog:
        client = str(client_id).strip()
        correlation = str(correlation_id).strip()
        if not client:
            raise ConnectorAuthorizationError(
                "Microsoft Graph metadata discovery requires a governed client boundary."
            )
        if not correlation:
            raise ValueError("Microsoft Graph metadata correlation id is required")

        now = float(self.clock())
        cached = self._cache.get(client)
        if cached is not None and cached.expires_at > now:
            return cached.catalog

        # Token acquisition resolves and validates the client -> tenant/application
        # boundary through the existing Microsoft credential architecture.  The
        # metadata document itself remains provider-global structural evidence.
        token = self.tokens.acquire_for_client(
            client_id=client,
            correlation_id=correlation,
        )
        access_token = str(getattr(token, "access_token", "")).strip()
        if not access_token or any(character.isspace() for character in access_token):
            raise ConnectorAuthorizationError(
                "Microsoft Graph metadata token is unavailable or malformed."
            )

        request = build_governed_request(
            MicrosoftCloudRequest(
                service=MicrosoftService.GRAPH,
                method="GET",
                path="/$metadata",
                permission_profile_name=self.permission_profile_name,
                mode=MicrosoftOperationMode.READ,
            )
        )
        metadata = self.transport.request_text(
            method=request.method,
            url=request.url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/xml",
            },
            timeout_seconds=self.timeout_seconds,
        )
        catalog = discover_graph_resources(
            metadata,
            source_reference="microsoft-graph:v1.0:$metadata",
        )
        self._cache[client] = _CachedCatalog(
            catalog=catalog,
            expires_at=now + self.cache_ttl_seconds,
        )
        return catalog

    def invalidate_client(self, client_id: str) -> None:
        client = str(client_id).strip()
        if client:
            self._cache.pop(client, None)
