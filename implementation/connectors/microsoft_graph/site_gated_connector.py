"""Mandatory site gate wrapper for the future activated SharePoint adapter.

Activation MUST register this wrapper, never the lower-level adapter directly.
The underlying adapter independently enforces requester/tenant/document rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from connectors.core.contracts import ConnectorRequest, ConnectorResult
from .site_access_registry import SharePointSiteAccess


class SharePointDelegate(Protocol):
    def execute(self, request: ConnectorRequest) -> ConnectorResult: ...
    def _tenant(self, context) -> str: ...


@dataclass(frozen=True)
class SiteGatedSharePointConnector:
    delegate: SharePointDelegate
    site_access: SharePointSiteAccess

    @property
    def provider_name(self):
        return self.delegate.provider_name

    @property
    def capabilities(self):
        return self.delegate.capabilities

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        # The existing delegate performs full verified identity/tenant binding;
        # a caller-supplied tenant selector is never accepted.
        tenant_id = self.delegate._tenant(request.context)
        if not isinstance(request.arguments, dict):
            raise ValueError("Exact SharePoint selectors required")
        site_id = request.arguments.get("site_id")
        if not isinstance(site_id, str) or not site_id:
            raise ValueError("Exact SharePoint site identifier required")
        self.site_access.require_site_access(
            tenant_id=tenant_id, site_id=site_id)
        # Re-read persisted access state per operation; no process cache.
        return self.delegate.execute(request)
