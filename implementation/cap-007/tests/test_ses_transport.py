from __future__ import annotations

import pytest

from jason_cap_007.service import EmailMessage
from jason_cap_007.ses import AwsSesConfig, AwsSesTransport, SesTransportError


class FakeAwsError(RuntimeError):
    def __init__(self, code: str, message: str = "sensitive provider message") -> None:
        super().__init__(message)
        self.response = {"Error": {"Code": code, "Message": message}}


class FailingClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def send_email(self, **kwargs):
        del kwargs
        raise self.error


def _message() -> EmailMessage:
    return EmailMessage(
        sender="jason@teamaot.com",
        to=("recipient@example.com",),
        subject="test subject",
        text_body="test body",
    )


def _credentials():
    return {
        "access_key_id": "test-access-key",
        "secret_access_key": "test-secret-key",
    }


def test_access_denied_is_reduced_to_safe_error_code():
    error = FakeAwsError("AccessDeniedException")
    transport = AwsSesTransport(
        config=AwsSesConfig(region_name="us-east-1"),
        client_factory=lambda **kwargs: FailingClient(error),
    )

    with pytest.raises(SesTransportError) as captured:
        transport.send(message=_message(), credentials=_credentials())

    assert captured.value.error_code == "EMAIL_SES_ACCESS_DENIED"
    assert str(captured.value) == "AWS SES send failed."
    assert "sensitive provider message" not in str(captured.value)


def test_message_rejected_is_reduced_to_safe_error_code():
    error = FakeAwsError("MessageRejected")
    transport = AwsSesTransport(
        config=AwsSesConfig(region_name="us-east-1"),
        client_factory=lambda **kwargs: FailingClient(error),
    )

    with pytest.raises(SesTransportError) as captured:
        transport.send(message=_message(), credentials=_credentials())

    assert captured.value.error_code == "EMAIL_SES_MESSAGE_REJECTED"


def test_unknown_provider_error_does_not_leak_provider_code_or_message():
    error = FakeAwsError("UnexpectedSecretBearingProviderFailure")
    transport = AwsSesTransport(
        config=AwsSesConfig(region_name="us-east-1"),
        client_factory=lambda **kwargs: FailingClient(error),
    )

    with pytest.raises(SesTransportError) as captured:
        transport.send(message=_message(), credentials=_credentials())

    assert captured.value.error_code == "EMAIL_SES_SEND_FAILED"
    assert "UnexpectedSecretBearingProviderFailure" not in str(captured.value)
    assert "sensitive provider message" not in str(captured.value)


def test_successful_send_returns_provider_message_id():
    class SuccessfulClient:
        def send_email(self, **kwargs):
            assert kwargs["FromEmailAddress"] == "jason@teamaot.com"
            return {"MessageId": "message-123"}

    transport = AwsSesTransport(
        config=AwsSesConfig(region_name="us-east-1"),
        client_factory=lambda **kwargs: SuccessfulClient(),
    )

    result = transport.send(message=_message(), credentials=_credentials())

    assert result.provider == "aws-ses"
    assert result.message_id == "message-123"
    assert result.accepted is True
