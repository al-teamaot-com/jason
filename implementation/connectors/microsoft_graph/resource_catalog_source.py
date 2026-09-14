"""Governed Microsoft Graph structural catalog source.

Microsoft publishes the Graph CSDL metadata document at the fixed service root.  This
source treats that document as provider-global structural metadata, not tenant data.
No client token is required to learn entity-set/field structure. Tenant authorization
is still mandatory later, inside the actual resource connector, before any operational
Microsoft data is read.

Entity-set and field names are learned from Microsoft metadata; none are enumerated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Callable, Protocol

from connectors.core.contracts import ConnectorAuthorizationError
from connectors.core.resource_catalog import ProviderResourceCatalog

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


@dataclass(frozen=True, slots=True)
class _CachedCatalog:
    catalog: MicrosoftGraphResourceCatalog
    expires_at: float


@dataclass(slots=True)
class MicrosoftGraphMetadataCatalogSource:
    """Resolve bounded provider-global Graph schema from Microsoft's metadata root."""

    transport: MicrosoftGraphMetadataTextTransport
    permission_profile_name: str = "directory-read"
    timeout_seconds: float = 20.0
    cache_ttl_seconds: int = 3600
    clock: Callable[[], float] = monotonic
    provider_id: str = field(default="microsoft_graph", init=False)
    _cache: _CachedCatalog | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.permission_profile_name.strip():
            raise ValueError("Microsoft metadata permission profile is required")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("Microsoft metadata timeout must be between 0 and 60 seconds")
        if self.cache_ttl_seconds < 60 or self.cache_ttl_seconds > 86400:
            raise ValueError("Microsoft metadata cache ttl must be between 60 and 86400 seconds")

    def catalog(self, *, correlation_id: str) -> MicrosoftGraphResourceCatalog:
        """Return provider-global structural metadata without accessing tenant data."""

        correlation = str(correlation_id).strip()
        if not correlation:
            raise ValueError("Microsoft Graph metadata correlation id is required")

        now = float(self.clock())
        cached = self._cache
        if cached is not None and cached.expires_at > now:
            return cached.catalog

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
            headers={"Accept": "application/xml"},
            timeout_seconds=self.timeout_seconds,
        )
        catalog = discover_graph_resources(
            metadata,
            source_reference="microsoft-graph:v1.0:$metadata",
        )
        self._cache = _CachedCatalog(
            catalog=catalog,
            expires_at=now + self.cache_ttl_seconds,
        )
        return catalog

    def provider_catalog(self, *, correlation_id: str) -> ProviderResourceCatalog:
        """Expose provider-global structure through Jason's generic catalog contract."""

        return self.catalog(correlation_id=correlation_id).provider_resource_catalog()

    def catalog_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> MicrosoftGraphResourceCatalog:
        """Return structure for a data read that already named a governed client.

        This validates only that the caller supplied a client scope.  The connector's
        token provider validates the actual client -> tenant/application boundary before
        operational data is accessed.
        """

        if not str(client_id).strip():
            raise ConnectorAuthorizationError(
                "Microsoft Graph resource reads require a governed client boundary."
            )
        return self.catalog(correlation_id=correlation_id)

    def provider_catalog_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> ProviderResourceCatalog:
        return self.catalog_for_client(
            client_id=client_id,
            correlation_id=correlation_id,
        ).provider_resource_catalog()

    def invalidate(self) -> None:
        self._cache = None

    def invalidate_client(self, client_id: str) -> None:
        # Metadata is provider-global; invalidating one tenant boundary invalidates the
        # structural cache without retaining any client identifier.
        if str(client_id).strip():
            self.invalidate()
