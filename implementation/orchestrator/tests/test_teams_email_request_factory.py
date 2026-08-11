from __future__ import annotations

from dataclasses import dataclass, field

from jason_cap_007.kernel_registration import email_send_capability
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.identity_authority import (
    AuthorityGrant,
    IdentityAuthorityService,
    IdentityRecord,
    InMemoryApprovalRepository,
    InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository,
    PermissionMode,
)
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    TeamsConversationPrincipalEvidence,
)
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory


@dataclass
class Contexts:
    records: dict[str, object] = field(default_factory=dict)

    def put_context(self, context):
        self.records[context.context_id] = context


def test_authenticated_email_imperative_creates_formal_approval_and_idempotency_key():
    identities = InMemoryIdentityRepository()
    grants = InMemoryAuthorityGrantRepository()
    approvals = InMemoryApprovalRepository()
    contexts = Contexts()

    identities.put(
        IdentityRecord(
            identity_id="person-al",
            identity_type="human",
            organization_id="aot",
        )
    )
    grants.put(
        AuthorityGrant(
            grant_id="grant-email-send",
            subject_id="person-al",
            capability="communication.email.send",
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.EXECUTE,
            approval_required=True,
        )
    )
    authority = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=approvals,
        contexts=contexts,
    )
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    capabilities.register(email_send_capability())

    factory = GovernedTeamsOrchestrationRequestFactory(
        authority=authority,
        capabilities=capabilities,
        approvals=approvals,
        execution_id_factory=lambda: "exec-email-1",
        correlation_id_factory=lambda: "corr-email-1",
        idempotency_key_factory=lambda: "idem-email-1",
        approval_id_factory=lambda: "approval-email-1",
    )

    request = factory.build(
        principal=BoundConversationPrincipal(
            principal_id="person-al",
            organization_id="aot",
            email_address="al@example.com",
        ),
        intent=ConversationIntent(
            capability_name="communication.email.send",
            capability_version="0.1",
            arguments={
                "to": ["al@example.com"],
                "subject": "Message from Jason",
                "text_body": "You asked Jason to send you an email.",
            },
            execution_mode="deterministic",
            permission_mode="execute",
            risk="high",
        ),
        identity=TeamsConversationPrincipalEvidence(
            microsoft_tenant_id="tenant-1",
            microsoft_object_id="object-1",
            authentication_assurance="botframework-authenticated",
            conversation_id="conversation-1",
            message_id="message-1",
        ),
    )

    approval = approvals.get("approval-email-1")
    assert approval is not None
    assert approval.status == "approved"
    assert approval.request_id == "exec-email-1"
    assert approval.requested_by == "person-al"
    assert approval.decided_by == "person-al"

    assert request.approval_present is True
    assert request.authority_allowed is True
    assert request.permission_mode == "execute"
    assert request.allow_pilot_capability is True
    assert request.allow_pilot_provider is True
    assert request.idempotency_key == "idem-email-1"
    assert request.authority_context_id in contexts.records
