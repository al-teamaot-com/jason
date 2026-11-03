"""Unregistered provider-neutral SharePoint read manifest.

Do not register/activate until the associated authorizer and release gate
are proven against real authorized and forbidden sites.
"""
from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationManifest, IntegrationOperation, OperationKind,
    ResourceDefinition, ResourceObservation, SelectorDefinition,
)
from orchestrator.provider_read_capability_catalog import MICROSOFT_GRAPH_PROVIDER


def build_sharepoint_read_manifest() -> IntegrationManifest:
    common = (
        SelectorDefinition("site_id", "Verified permitted Microsoft SharePoint site identifier.",
                           verified_identity_required=True),
        SelectorDefinition("drive_id", "Verified document library identifier.",
                           verified_identity_required=True),
        SelectorDefinition("item_id", "Verified document identifier.",
                           verified_identity_required=True),
        SelectorDefinition("folder_id", "Optional verified folder identifier."),
    )
    return IntegrationManifest(
        integration_id="microsoft_graph_sharepoint_reader",
        display_name="Reusable Governed SharePoint Reader",
        manifest_version="1.0",
        provider_id=MICROSOFT_GRAPH_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="knowledge_library",
                description="Approved SharePoint site document libraries.",
                selectors=common,
                operations=(
                    IntegrationOperation(
                        operation_id="knowledge.library.search",
                        kind=OperationKind.SEARCH,
                        capability_name="knowledge.library.search",
                        description="Enumerate bounded libraries from one explicitly authorized SharePoint site.",
                        read_only=True,
                        selector_names=("site_id",),
                        collection_supported=True,
                    ),
                ),
                observations=(
                    ResourceObservation("document_library", "Verified site-bound document library metadata."),
                ),
                relationships=("site -> library",),
            ),
            ResourceDefinition(
                resource_type="knowledge_document",
                description="Authorized SharePoint documents and metadata.",
                selectors=common,
                operations=(
                    IntegrationOperation(
                        operation_id="knowledge.document.search",
                        kind=OperationKind.SEARCH,
                        capability_name="knowledge.document.search",
                        description="List bounded file/folder metadata within an authorized document library.",
                        read_only=True,
                        selector_names=("site_id", "drive_id", "folder_id"),
                        collection_supported=True,
                    ),
                    IntegrationOperation(
                        operation_id="knowledge.document.metadata.read",
                        kind=OperationKind.READ,
                        capability_name="knowledge.document.metadata.read",
                        description="Read verified metadata for one permitted document.",
                        read_only=True,
                        selector_names=("site_id", "drive_id", "item_id"),
                    ),
                    IntegrationOperation(
                        operation_id="knowledge.document.content.read",
                        kind=OperationKind.READ,
                        capability_name="knowledge.document.content.read",
                        description="Read bounded document content only after explicit sensitive-information release.",
                        read_only=True,
                        selector_names=("site_id", "drive_id", "item_id"),
                    ),
                ),
                observations=(
                    ResourceObservation("document_metadata", "Source, version, size and bounded information."),
                ),
                relationships=("site -> library -> document",),
            ),
        ),
    )
