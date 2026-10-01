from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationManifest,
    IntegrationOperation,
    OperationKind,
    ResourceDefinition,
    ResourceObservation,
    SelectorDefinition,
)
from orchestrator.provider_read_capability_catalog import (
    COMMUNICATION_MAILBOX_AUDIT_SEARCH,
    MICROSOFT_PURVIEW_PROVIDER,
)


def build_microsoft_purview_manifest() -> IntegrationManifest:
    return IntegrationManifest(
        integration_id="microsoft_purview_mail_investigation",
        display_name="Microsoft Purview Exchange Audit Investigation",
        manifest_version="1.0",
        provider_id=MICROSOFT_PURVIEW_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="communication_mailbox_audit",
                description="Bounded Exchange mailbox audit evidence for CAP-003.",
                selectors=(
                    SelectorDefinition("mailbox", "Exact target mailbox address."),
                    SelectorDefinition("start", "UTC lower time bound."),
                    SelectorDefinition("end", "UTC upper time bound."),
                    SelectorDefinition("subject", "Optional subject substring."),
                    SelectorDefinition("internet_message_id", "Optional exact Internet Message ID."),
                    SelectorDefinition("operations", "Optional bounded CAP-003 Exchange audit operations."),
                    SelectorDefinition("maximum_records", "Maximum bounded audit records."),
                ),
                operations=(
                    IntegrationOperation(
                        operation_id="communication.mailbox.audit.search",
                        kind=OperationKind.SEARCH,
                        capability_name=COMMUNICATION_MAILBOX_AUDIT_SEARCH,
                        description="Search Purview Exchange audit evidence for move/delete/update attribution.",
                        read_only=True,
                        selector_names=(
                            "mailbox",
                            "start",
                            "end",
                            "subject",
                            "internet_message_id",
                            "operations",
                            "maximum_records",
                        ),
                        collection_supported=True,
                    ),
                ),
                observations=(
                    ResourceObservation(
                        "mailbox_actor",
                        "Actor, operation, time, client/IP/app/device, mailbox owner, folder, and affected message identifiers.",
                    ),
                ),
                relationships=("mailbox audit event -> mailbox message",),
            ),
        ),
        metadata={
            "mode": "read_only",
            "transport": "microsoft_graph_purview_audit_search_v1",
            "tenant_selection": "kernel_client_boundary_only",
            "permission_profile": "mail-investigation-read",
        },
    )
