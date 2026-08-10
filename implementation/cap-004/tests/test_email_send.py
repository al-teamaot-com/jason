from __future__ import annotations

from dataclasses import dataclass

import pytest

from jason_cap_004 import (
    CAPABILITY_NAME,
    SES_PROVIDER_ID,
    SES_SECRET_NAME,
    EmailSendPolicy,
    EmailSenderDeniedError,
    EmailValidationError,
    GovernedEmailSendInvoker,
    ProviderSendResult,
    SecretLease,
)


@dataclass
class FakeResolution:
    capability_name: str = CAPABILITY_NAME
    selected_provider_id: str = SES_PROVIDER_ID


@dataclass
class FakeRequest:
    execution_id: str = "exec-1"
    correlation_id: str = "corr-1"
    principal_id: str = "person-al"
    organization_id: str = "aot"
    client_id: str | None = None
    capability_name: str = CAPABILITY_NAME
    arguments: dict = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = {}


class FakeSecrets:
    def __init__(self):
        self.requests = []
        self.revoked = []

    def resolve(self, **kwargs):
        self.requests.append(kwargs)
        return SecretLease(
            values={"access_key_id": "AKIA_TEST", "secret_access_key": "secret-test"},
            lease_id="lease-1",
        )

    def revoke(self, lease):
        self.revoked.append(lease)


class FakeTransport:
    provider_id = SES_PROVIDER_ID

    def __init__(self):
        self.calls = []
        self.fail = False

    def send(self, *, message, credentials):
        self.calls.append((message, dict(credentials)))
        if self.fail:
            raise RuntimeError("synthetic provider failure")
        return ProviderSendResult(provider=SES_PROVIDER_ID, message_id="ses-message-1")


class FakeAudit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


def invoker():
    secrets = FakeSecrets()
    transport = FakeTransport()
    audit = FakeAudit()
    service = GovernedEmailSendInvoker(
        secrets=secrets,
        transport=transport,
        policy=EmailSendPolicy(default_sender="jason@teamaot.com"),
        audit=audit,
    )
    return service, secrets, transport, audit


def test_send_uses_logical_secret_and_returns_redacted_metadata():
    service, secrets, transport, audit = invoker()
    request = FakeRequest(
        arguments={
            "to": ["al@teamaot.com"],
            "subject": "CAP-004 test",
            "text_body": "Hello from Jason",
        }
    )

    result = service.invoke(request=request, resolution=FakeResolution())

    assert result.output["provider"] == SES_PROVIDER_ID
    assert result.output["message_id"] == "ses-message-1"
    assert result.output["recipient_count"] == 1
    assert "text_body" not in result.output
    assert "secret_access_key" not in result.output
    assert secrets.requests[0]["secret_name"] == SES_SECRET_NAME
    assert secrets.revoked[0].lease_id == "lease-1"
    assert transport.calls[0][0].sender == "jason@teamaot.com"
    assert [event[0] for event in audit.events] == [
        "email.send.attempted",
        "email.send.completed",
    ]


def test_audit_events_exclude_message_bodies_recipients_and_secret_values():
    service, _, _, audit = invoker()
    body_secret = "BODY-SENSITIVE-MARKER"
    credential_secret = "secret-test"
    recipient = "al@teamaot.com"
    request = FakeRequest(
        arguments={
            "to": [recipient],
            "subject": "Sensitive subject text",
            "text_body": body_secret,
            "html_body": f"<p>{body_secret}</p>",
        }
    )

    service.invoke(request=request, resolution=FakeResolution())

    rendered = repr(audit.events)
    assert body_secret not in rendered
    assert credential_secret not in rendered
    assert "AKIA_TEST" not in rendered
    assert recipient not in rendered
    assert "Sensitive subject text" not in rendered
    for _, payload in audit.events:
        assert payload["recipient_count"] == 1
        assert payload["sender"] == "jason@teamaot.com"
        assert len(payload["subject_sha256"]) == 64


def test_provider_failure_emits_safe_failure_event_and_revokes_lease():
    service, secrets, transport, audit = invoker()
    transport.fail = True
    request = FakeRequest(
        arguments={
            "to": "al@teamaot.com",
            "subject": "provider failure",
            "text_body": "sensitive failure body",
        }
    )

    with pytest.raises(RuntimeError):
        service.invoke(request=request, resolution=FakeResolution())

    assert secrets.revoked[0].lease_id == "lease-1"
    assert audit.events[-1][0] == "email.send.failed"
    assert audit.events[-1][1]["error_code"] == "EMAIL_CAPABILITY_FAILED"
    assert "sensitive failure body" not in repr(audit.events)


def test_provider_credentials_are_rejected_from_request_arguments():
    service, _, transport, audit = invoker()
    request = FakeRequest(
        arguments={
            "to": "al@teamaot.com",
            "subject": "bad",
            "text_body": "bad",
            "access_key_id": "should-not-be-here",
        }
    )

    with pytest.raises(EmailValidationError):
        service.invoke(request=request, resolution=FakeResolution())

    assert not transport.calls
    assert not audit.events


def test_sender_must_be_policy_allowed():
    service, _, transport, audit = invoker()
    request = FakeRequest(
        arguments={
            "to": "al@teamaot.com",
            "subject": "bad sender",
            "text_body": "hello",
            "from_address": "someone@example.com",
        }
    )

    with pytest.raises(EmailSenderDeniedError):
        service.invoke(request=request, resolution=FakeResolution())

    assert not transport.calls
    assert not audit.events


def test_body_required():
    service, _, _, audit = invoker()
    request = FakeRequest(arguments={"to": "al@teamaot.com", "subject": "no body"})

    with pytest.raises(EmailValidationError):
        service.invoke(request=request, resolution=FakeResolution())

    assert not audit.events
