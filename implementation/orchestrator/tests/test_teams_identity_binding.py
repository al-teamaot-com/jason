from dataclasses import dataclass, field

from kernel.identity_authority import IdentityRecord
from orchestrator.teams_conversation_flow import TeamsConversationPrincipalEvidence
from orchestrator.teams_identity_binding import (
    JasonTeamsIdentityBinder,
    MicrosoftIdentityBinding,
)


@dataclass
class Bindings:
    records: dict[tuple[str, str], MicrosoftIdentityBinding] = field(default_factory=dict)

    def find(self, *, microsoft_tenant_id, microsoft_object_id):
        return self.records.get((microsoft_tenant_id, microsoft_object_id))


@dataclass
class Identities:
    records: dict[str, IdentityRecord] = field(default_factory=dict)

    def get(self, identity_id):
        return self.records.get(identity_id)


def evidence(*, tenant="tenant-1", object_id="object-1", assurance="botframework-authenticated"):
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id=tenant,
        microsoft_object_id=object_id,
        authentication_assurance=assurance,
        conversation_id="conversation-1",
        message_id="message-1",
    )


def binder(*, binding_status="active", identity_status="active"):
    binding = MicrosoftIdentityBinding(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        jason_identity_id="jason-user-1",
        client_id=None,
        status=binding_status,
    )
    identity = IdentityRecord(
        identity_id="jason-user-1",
        identity_type="human",
        organization_id="aot",
        status=identity_status,
    )
    return JasonTeamsIdentityBinder(
        bindings=Bindings({("tenant-1", "object-1"): binding}),
        identities=Identities({"jason-user-1": identity}),
    )


def test_binds_authenticated_microsoft_identity_to_existing_jason_principal():
    principal = binder().bind(evidence())
    assert principal is not None
    assert principal.principal_id == "jason-user-1"
    assert principal.organization_id == "aot"
    assert principal.client_id is None


def test_unknown_microsoft_identity_fails_closed():
    assert binder().bind(evidence(object_id="unknown")) is None


def test_wrong_tenant_cannot_reuse_object_binding():
    assert binder().bind(evidence(tenant="other-tenant")) is None


def test_untrusted_authentication_assurance_fails_closed():
    assert binder().bind(evidence(assurance="transport-claimed")) is None


def test_disabled_binding_fails_closed():
    assert binder(binding_status="disabled").bind(evidence()) is None


def test_disabled_jason_identity_fails_closed():
    assert binder(identity_status="disabled").bind(evidence()) is None


def test_missing_jason_identity_fails_closed():
    bindings = Bindings({
        ("tenant-1", "object-1"): MicrosoftIdentityBinding(
            microsoft_tenant_id="tenant-1",
            microsoft_object_id="object-1",
            jason_identity_id="missing",
        )
    })
    assert JasonTeamsIdentityBinder(bindings=bindings, identities=Identities()).bind(evidence()) is None
