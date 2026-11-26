"""Dormant-by-default, tenant-bound SharePoint canonical read contracts."""
from __future__ import annotations

from datetime import datetime

from kernel.capabilities import CapabilityRegistryService
from kernel.execution_providers import ExecutionProviderRegistryService
from .provider_read_capability_catalog import _provider, _read_capability

SHAREPOINT_PROVIDER = "microsoft_graph_sharepoint"
SHAREPOINT_CAPABILITIES = frozenset({
    "knowledge.library.search",
    "knowledge.document.search",
    "knowledge.document.metadata.read",
    "knowledge.document.content.read",
})


def register_sharepoint_read_foundation(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService, now: datetime,
) -> None:
    definitions = (
        ("knowledge.library.search", "Search AOT SharePoint Libraries", "knowledge_library", "search",
         "site_id", "SharePoint site libraries drives documents"),
        ("knowledge.document.search", "Search AOT SharePoint Folder", "knowledge_document", "search",
         "site_id,drive_id,folder_id", "SharePoint document folder listing"),
        ("knowledge.document.metadata.read", "Read SharePoint Document Metadata",
         "knowledge_document", "read", "site_id,drive_id,item_id",
         "SharePoint file metadata"),
        ("knowledge.document.content.read", "Read Approved SharePoint Document",
         "knowledge_document", "read", "site_id,drive_id,item_id",
         "SharePoint content separately authorized sensitive file"),
    )
    for name, display, resource, op, selectors, hints in definitions:
        capabilities.register(_read_capability(
            now=now, capability_name=name, display_name=display,
            business_purpose="Read only authorized AOT-owned SharePoint resources.",
            resource_types=resource, operation=op, selector_keys=selectors,
            fact_hints=hints,
            authoritative_change_sources=("Microsoft Graph v1.0 Sites API",),
            client_isolation_required=False,
        ))
    providers.register(_provider(
        now=now, provider_id=SHAREPOINT_PROVIDER,
        display_name="AOT SharePoint Dedicated App-Only Reader",
        capabilities=SHAREPOINT_CAPABILITIES,
        authority="aot_sharepoint",
        vendor_change_sources=("Microsoft Graph v1.0 Sites API",),
    ))
