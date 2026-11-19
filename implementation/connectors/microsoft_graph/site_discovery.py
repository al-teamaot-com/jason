"""App-only daily AOT SharePoint site discovery; no site access is auto-granted.

Caller must bind a validated AOT tenant and the dedicated Jason SharePoint
application token provider. The host scheduler invokes run() once daily.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from connectors.core.contracts import ConnectorTransportError, HttpTransport
from .site_access_registry import SharePointSiteAccess


class AppOnlyTokens(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


@dataclass(frozen=True)
class SharePointSiteDiscovery:
    tenant_id: str
    tokens: AppOnlyTokens
    transport: HttpTransport
    registry: SharePointSiteAccess
    allowed_sharepoint_hosts: frozenset[str] = frozenset({"absolnet.sharepoint.com"})
    max_pages: int = 1000
    max_sites: int = 100000

    def __post_init__(self):
        UUID(self.tenant_id)
        if self.tenant_id != self.registry.tenant_id:
            raise PermissionError("Site registry tenant binding mismatch")
        if not self.allowed_sharepoint_hosts or any(
            not host or host != host.casefold() or not host.endswith(".sharepoint.com")
            for host in self.allowed_sharepoint_hosts
        ):
            raise PermissionError("Explicit AOT SharePoint hostnames required")
        if not (1 <= self.max_pages <= 1000 and 1 <= self.max_sites <= 100000):
            raise ValueError("Discovery limits invalid")

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com"
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.path not in {
                    "/v1.0/sites/getAllSites", "/v1.0/sites/oneDrive.getAllSites"
                }):
            raise ConnectorTransportError("Untrusted Graph site pagination URL")
        return url

    def run(self) -> int:
        """Register sites only after every Graph page succeeds."""
        try:
            token = self.tokens.access_token_for_tenant(microsoft_tenant_id=self.tenant_id)
            if not isinstance(token, str) or not token.strip():
                raise PermissionError("Dedicated SharePoint app token unavailable")
            headers = {"Authorization": "Bearer " + token.strip()}
            next_url = "https://graph.microsoft.com/v1.0/sites/getAllSites"
            seen_urls = set()
            discovered = {}
            for _ in range(self.max_pages):
                self._validate_url(next_url)
                if next_url in seen_urls:
                    raise ConnectorTransportError("Graph pagination cycle")
                seen_urls.add(next_url)
                page = self.transport.request(
                    method="GET", url=next_url, headers=headers,
                    params=None, timeout_seconds=20,
                )
                if not isinstance(page, Mapping) or not isinstance(page.get("value"), list):
                    raise ConnectorTransportError("Invalid site discovery response")
                for entry in page["value"]:
                    if not isinstance(entry, Mapping):
                        raise ConnectorTransportError("Invalid site object")
                    if entry.get("isPersonalSite") is True:
                        continue
                    site_id, name, web_url = entry.get("id"), entry.get("name"), entry.get("webUrl")
                    if not all(isinstance(x, str) and x.strip() for x in (site_id, name, web_url)):
                        raise ConnectorTransportError("Incomplete site identity")
                    host = urlsplit(web_url)
                    if (host.scheme != "https" or host.hostname not in self.allowed_sharepoint_hosts
                            or host.username is not None or host.password is not None
                            or host.port is not None):
                        raise ConnectorTransportError("Site outside configured AOT SharePoint hosts")
                    discovered[site_id] = {
                        "tenant_id": self.tenant_id, "site_id": site_id,
                        "name": name, "web_url": web_url,
                    }
                    if len(discovered) > self.max_sites:
                        raise ConnectorTransportError("Site discovery exceeds bounded count")
                new_link = page.get("@odata.nextLink")
                if not new_link:
                    return self.registry.discover(discovered.values())
                if not isinstance(new_link, str):
                    raise ConnectorTransportError("Invalid pagination continuation")
                next_url = new_link
            raise ConnectorTransportError("Site discovery pagination limit exceeded")
        except Exception as exc:
            self.registry.discovery_failed(type(exc).__name__)
            raise
