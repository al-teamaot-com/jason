from __future__ import annotations

from dataclasses import dataclass, field

import pytest

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
from orchestrator.teams_request_factory import (
    ConversationApprovalRequired,
    ConversationAuthorityError,
    GovernedTeamsOrchestrationRequestFactory,
)


@dataclass
class Contexts:
    records: dict[str, object] = field(default_factory=dict)

    def put_context(self, context):
        self.records[context.context_id] = context


def identity_evidence():
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        authentication_assurance="botframework-authenticated",
        conversation_id="conversation-1",
        message_id="message-1",
    )


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def intent(*, permission_mode="observe"):
    return ConversationIntent(
        capability_name="endpoint.device.search",
        arguments={
            "hostname": "AOT-50282",
            "requested_facts": ("last logged in user",),
        },
        execution_mode="deterministic",
        permission_mode=permission_mode,
        risk="low",
    )


def authority(*, grant=True, approval_required=False, permission=PermissionMode.OBSERVE):
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
    if grant:
        grants.put(
            AuthorityGrant(
                grant_id="grant-endpoint-read",
                subject_id="person-al",
                capability="endpoint.device.search",
                organization_id="aot",
                client_id=None,
                permission=permission,
                approval_required=approval_required,
            )
        )
    return (
        IdentityAuthorityService(
            identities=identities,
            grants=grants,
            approvals=approvals,
            contexts=contexts,
        ),
        contexts,
    )


def factory(service):
    return GovernedTeamsOrchestrationRequestFactory(
        authority=service,
        execution_id_factory=lambda: "exec-teams-1",
        correlation_id_factory=lambda: "corr-teams-1",
    )


def test_factory_requires_jason_authority_and_preserves_execution_context():
    service, contexts = authority()

    request = factory(service).build(
        principal=principal(),
        intent=intent(),
        identity=identity_evidence(),
            correlation_id="corr-teams-1",
    )

    assert request.principal_id == "person-al"
    assert request.organization_id == "aot"
    assert request.capability_name == "endpoint.device.search"
    assert request.requested_mode == "deterministic"
    assert request.permission_mode == "observe"
    assert request.requester_kind == "human"
    assert request.authority_allowed is True
    assert request.approval_present is False
    assert request.authority_context_id in contexts.records
    context = contexts.records[request.authority_context_id]
    assert context.capability == "endpoint.device.search"
    assert context.requested_mode is PermissionMode.OBSERVE
    assert context.authentication_assurance == "botframework-authenticated"


def test_factory_fails_closed_without_matching_authority_grant():
    service, _ = authority(grant=False)

    with pytest.raises(ConversationAuthorityError) as error:
        factory(service).build(
            principal=principal(),
            intent=intent(),
            identity=identity_evidence(),
            correlation_id="corr-teams-1",
        )

    assert error.value.code == "AUTHORITY_DENIED"
    assert error.value.reason_codes == ("NO_MATCHING_AUTHORITY_GRANT",)


def test_factory_surfaces_approval_requirement_without_execution_context():
    service, contexts = authority(approval_required=True)

    with pytest.raises(ConversationApprovalRequired) as error:
        factory(service).build(
            principal=principal(),
            intent=intent(),
            identity=identity_evidence(),
            correlation_id="corr-teams-1",
        )

    assert error.value.code == "APPROVAL_REQUIRED"
    assert contexts.records == {}


def test_factory_refuses_silent_authority_downgrade():
    service, _ = authority(permission=PermissionMode.RECOMMEND)

    with pytest.raises(ConversationAuthorityError) as error:
        factory(service).build(
            principal=principal(),
            intent=intent(permission_mode="execute"),
            identity=identity_evidence(),
            correlation_id="corr-teams-1",
        )

    assert error.value.code == "AUTHORITY_DENIED"
    assert error.value.reason_codes == ("AUTHORITY_MODE_EXCEEDED",)
