"""AOT SharePoint site policy and independent document-content release checks.

A site enabled in Grafana grants Jason's validated AOT workload site browsing,
not unrestricted release of financial/sensitive file contents to arbitrary users.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .site_access_registry import SharePointSiteAccess


class ExactContentRelease(Protocol):
    def authorized(self, *, principal_id: str, organization_id: str,
                   client_id: str | None, tenant_id: str, operation: str,
                   site_id: str, drive_id: str | None, item_id: str | None) -> bool: ...


@dataclass(frozen=True, slots=True)
class AotSharePointSiteDocumentAuthorizer:
    site_access: SharePointSiteAccess
    approved_service_principals: frozenset[str]
    content_release: ExactContentRelease

    _metadata_operations = frozenset({
        "knowledge.library.search",
        "knowledge.document.search",
        "knowledge.document.metadata.read",
    })

    def authorized(self, *, principal_id: str, organization_id: str,
                   client_id: str | None, tenant_id: str, operation: str,
                   site_id: str, drive_id: str | None, item_id: str | None) -> bool:
        if (organization_id != "aot" or client_id is not None
                or principal_id not in self.approved_service_principals):
            return False
        try:
            self.site_access.require_site_access(
                tenant_id=tenant_id, site_id=site_id)
        except (PermissionError, ValueError):
            return False
        if operation in self._metadata_operations:
            return True
        if operation != "knowledge.document.content.read":
            return False
        return self.content_release.authorized(
            principal_id=principal_id, organization_id=organization_id,
            client_id=client_id, tenant_id=tenant_id, operation=operation,
            site_id=site_id, drive_id=drive_id, item_id=item_id,
        ) is True
