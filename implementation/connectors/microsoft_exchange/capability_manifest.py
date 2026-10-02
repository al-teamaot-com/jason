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
    COMMUNICATION_MAIL_TRACE_SEARCH,
    COMMUNICATION_MAIL_TRACE_DETAIL,
    COMMUNICATION_MAILBOX_FORWARDING_READ,
    COMMUNICATION_MAILBOX_INBOX_RULES_READ,
    COMMUNICATION_MAILBOX_FULL_ACCESS_READ,
    COMMUNICATION_MAILBOX_SEND_AS_READ,
    COMMUNICATION_MAILBOX_SEND_ON_BEHALF_READ,
    COMMUNICATION_MAILBOX_TRANSPORT_RULES_READ,
    COMMUNICATION_MAILBOX_MOBILE_DEVICES_READ,
    COMMUNICATION_MAILBOX_RETENTION_AUDIT_READ,
    MICROSOFT_EXCHANGE_PROVIDER,
)


def build_microsoft_exchange_manifest() -> IntegrationManifest:
    mailbox = SelectorDefinition("mailbox", "Exact mailbox address inside the governed client tenant.")
    trace_id = SelectorDefinition(
        "message_trace_id",
        "Exact Exchange message trace identifier.",
        verified_identity_required=True,
    )
    recipient = SelectorDefinition("recipient", "Exact recipient address for one traced delivery.")
    return IntegrationManifest(
        integration_id="microsoft_exchange_mail_investigation",
        display_name="Microsoft Exchange Online Mail Investigation",
        manifest_version="1.0",
        provider_id=MICROSOFT_EXCHANGE_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="communication_mail_trace",
                description="Exchange Online mail-flow and delivery trace evidence.",
                selectors=(
                    SelectorDefinition("sender", "Optional exact sender address."),
                    SelectorDefinition("recipients", "Optional exact recipient address list."),
                    SelectorDefinition("subject", "Optional subject substring."),
                    SelectorDefinition("start", "UTC lower time bound."),
                    SelectorDefinition("end", "UTC upper time bound."),
                    SelectorDefinition("result_size", "Bounded maximum trace records."),
                    trace_id,
                    recipient,
                ),
                operations=(
                    IntegrationOperation(
                        operation_id="communication.mail.trace.search",
                        kind=OperationKind.SEARCH,
                        capability_name=COMMUNICATION_MAIL_TRACE_SEARCH,
                        description="Search Exchange Online Message Trace V2.",
                        read_only=True,
                        selector_names=("sender", "recipients", "subject", "start", "end", "result_size"),
                        collection_supported=True,
                    ),
                    IntegrationOperation(
                        operation_id="communication.mail.trace.detail",
                        kind=OperationKind.READ,
                        capability_name=COMMUNICATION_MAIL_TRACE_DETAIL,
                        description="Read processing events for one exact trace/recipient.",
                        read_only=True,
                        selector_names=("message_trace_id", "recipient"),
                    ),
                ),
                observations=(
                    ResourceObservation("mail_flow", "Delivery status, trace IDs, transport processing, and recipient handling."),
                ),
                relationships=("mail trace -> mailbox message",),
            ),
            ResourceDefinition(
                resource_type="communication_mailbox_posture",
                description="Read-only Exchange mailbox configuration evidence for a governed client mailbox.",
                selectors=(mailbox,),
                operations=(
                    IntegrationOperation(operation_id="communication.mailbox.forwarding.read",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_FORWARDING_READ,description="Read mailbox forwarding.",read_only=True,selector_names=("mailbox",)),
                    IntegrationOperation(operation_id="communication.mailbox.inbox_rules.read_hidden",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_INBOX_RULES_READ,description="Read visible and hidden Inbox rules.",read_only=True,selector_names=("mailbox",)),
                    IntegrationOperation(operation_id="communication.mailbox.full_access.read",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_FULL_ACCESS_READ,description="Read FullAccess delegates.",read_only=True,selector_names=("mailbox",)),
                    IntegrationOperation(operation_id="communication.mailbox.send_as.read",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_SEND_AS_READ,description="Read SendAs delegates.",read_only=True,selector_names=("mailbox",)),
                    IntegrationOperation(operation_id="communication.mailbox.send_on_behalf.read",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_SEND_ON_BEHALF_READ,description="Read SendOnBehalf delegates.",read_only=True,selector_names=("mailbox",)),
                    IntegrationOperation(operation_id="communication.mailbox.transport_rules.read",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_TRANSPORT_RULES_READ,description="Read tenant transport rules.",read_only=True,selector_names=()),
                    IntegrationOperation(operation_id="communication.mailbox.mobile_devices.read",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_MOBILE_DEVICES_READ,description="Read mailbox mobile-device state.",read_only=True,selector_names=("mailbox",)),
                    IntegrationOperation(operation_id="communication.mailbox.retention_audit_config.read",kind=OperationKind.READ,capability_name=COMMUNICATION_MAILBOX_RETENTION_AUDIT_READ,description="Read mailbox retention, hold, archive, and audit configuration.",read_only=True,selector_names=("mailbox",)),
                ),
                observations=(
                    ResourceObservation("mailbox_posture", "Forwarding, rules, delegates, mobile clients, transport rules, retention, and audit configuration."),
                ),
                relationships=("mailbox posture -> mail investigation",),
            ),
        ),
        metadata={
            "mode": "read_only",
            "transport": "governed_exchange_read_worker",
            "tenant_selection": "kernel_client_boundary_only",
            "permission_profile": "mail-investigation-read",
        },
    )
