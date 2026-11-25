"""Governed application service for Grafana SharePoint site switches.

No HTTP route and no Grafana direct database writes are introduced here.
An authenticated Jason API must supply its verified principal, never a user-
supplied impersonation claim, and enforce the existing exact-action policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .site_access_registry import SharePointSiteAccess


class SiteAdministrationAuthorizer(Protocol):
    def can_change_site_access(
        self, *, authenticated_principal: str, tenant_id: str,
        site_id: str, desired_enabled: bool, approval_reference: str,
    ) -> bool: ...


@dataclass(frozen=True)
class GovernedSiteAccessAdministration:
    registry: SharePointSiteAccess
    authorization: SiteAdministrationAuthorizer

    def list_sites(self) -> list[dict]:
        # An HTTP wrapper must independently authenticate/authorize reads;
        # never publish raw records from an anonymous Grafana data source.
        return self.registry.sites()

    def change_site_access(self, *, authenticated_principal: str,
                           site_id: str, enabled: bool,
                           approval_reference: str,
                           expected_revision: int) -> dict:
        if (not isinstance(authenticated_principal, str) or
                not authenticated_principal.strip() or type(enabled) is not bool):
            raise PermissionError("Authenticated exact-action principal required")
        if self.authorization.can_change_site_access(
            authenticated_principal=authenticated_principal,
            tenant_id=self.registry.tenant_id,
            site_id=site_id,
            desired_enabled=enabled,
            approval_reference=approval_reference,
        ) is not True:
            raise PermissionError("Site access change not authorized")
        revision = self.registry.set_enabled(
            site_id=site_id, enabled=enabled, actor=authenticated_principal,
            approval_reference=approval_reference,
            expected_revision=expected_revision,
        )
        updated = next((s for s in self.registry.sites()
                        if s["site_id"] == site_id), None)
        if updated is None or updated["revision"] != revision or bool(updated["enabled"]) != enabled:
            raise RuntimeError("SharePoint site configuration readback mismatch")
        return updated
