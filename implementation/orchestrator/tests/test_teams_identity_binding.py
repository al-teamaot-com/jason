from dataclasses import dataclass, field

import pytest

from connectors.core.contracts import ConnectorTransportError
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


@dataclass
class Directory:
    email: str | None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def resolve_email(self, *, microsoft_tenant_id, microsoft_object_id):
        self.calls.append((microsoft_tenant_id, microsoft_object_id))
        return self.email


@dataclass
class FailingDirectory:
    error: Exception
    calls: list[tuple[str, str]] = field(default_factory=list)

    def resolve_email(self, *, microsoft_tenant_id, microsoft_object_id):
        self.calls.append((microsoft_tenant_id, microsoft_object_id))
        raise self.error


def evidence(*, tenant="tenant-1", object_id="object-1", assurance="botframework-authenticated"):
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id=tenant,
        microsoft_object_id=object_id,
        authentication_assurance=assurance,
        conversation_id="conversation-1",
        message_id="message-1",
    )


def binder(*, binding_status="active", identity_status="active", email_address=None, directory=None):
    binding = MicrosoftIdentityBinding(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        jason_identity_id="jason-user-1",
        client_id=None,
        email_address=email_address,
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
        directory=directory,
    )


def test_binds_authenticated_microsoft_identity_to_existing_jason_principal():
    principal = binder().bind(evidence())
    assert principal is not None
    assert principal.principal_id == "jason-user-1"
    assert principal.organization_id == "aot"
    assert principal.client_id is None


def test_directory_resolves_email_from_authenticated_user_identity():
    directory = Directory("loggedin@teamaot.com")
    principal = binder(
        email_address="stale@teamaot.com",
        directory=directory,
    ).bind(evidence())

    assert principal is not None
    assert principal.email_address == "loggedin@teamaot.com"
    assert directory.calls == [("tenant-1", "object-1")]


def test_directory_result_overrides_stale_cached_binding_address():
    principal = binder(
        email_address="old@teamaot.com",
        directory=Directory("current@teamaot.com"),
    ).bind(evidence())
    assert principal is not None
    assert principal.email_address == "current@teamaot.com"


def test_directory_missing_email_does_not_fall_back_to_stale_binding():
    principal = binder(
        email_address="old@teamaot.com",
        directory=Directory(None),
    ).bind(evidence())
    assert principal is not None
    assert principal.email_address is None


def test_directory_transport_failure_does_not_invalidate_verified_identity_binding():
    directory = FailingDirectory(
        ConnectorTransportError(
            "HTTP transport failed with status 429",
            status_code=429,
            retry_after_seconds=30.0,
        )
    )
    principal = binder(
        email_address="stale@teamaot.com",
        directory=directory,
    ).bind(evidence())

    assert principal is not None
    assert principal.principal_id == "jason-user-1"
    assert principal.organization_id == "aot"
    assert principal.email_address is None
    assert directory.calls == [("tenant-1", "object-1")]


def test_directory_semantic_authority_failure_remains_fail_closed():
    directory = FailingDirectory(
        PermissionError("Microsoft Graph user identity did not match authenticated object")
    )
    with pytest.raises(PermissionError, match="did not match authenticated object"):
        binder(directory=directory).bind(evidence())


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
