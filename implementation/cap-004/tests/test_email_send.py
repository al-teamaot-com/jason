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

    def send(self, *, message, credentials):
        self.calls.append((message, dict(credentials)))
        return ProviderSendResult(provider=SES_PROVIDER_ID, message_id="ses-message-1")


def invoker():
    secrets = FakeSecrets()
    transport = FakeTransport()
    service = GovernedEmailSendInvoker(
        secrets=secrets,
        transport=transport,
        policy=EmailSendPolicy(default_sender="jason@teamaot.com"),
    )
    return service, secrets, transport


def test_send_uses_logical_secret_and_returns_redacted_metadata():
    service, secrets, transport = invoker()
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


def test_provider_credentials_are_rejected_from_request_arguments():
    service, _, transport = invoker()
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


def test_sender_must_be_policy_allowed():
    service, _, transport = invoker()
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


def test_body_required():
    service, _, _ = invoker()
    request = FakeRequest(arguments={"to": "al@teamaot.com", "subject": "no body"})

    with pytest.raises(EmailValidationError):
        service.invoke(request=request, resolution=FakeResolution())
