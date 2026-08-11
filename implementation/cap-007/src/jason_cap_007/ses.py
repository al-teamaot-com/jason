from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .service import EmailCapabilityError, EmailMessage, ProviderSendResult, SES_PROVIDER_ID


class SesTransportError(EmailCapabilityError):
    error_code = "EMAIL_SES_SEND_FAILED"


@dataclass(frozen=True, slots=True)
class AwsSesConfig:
    region_name: str

    def __post_init__(self) -> None:
        if not self.region_name.strip():
            raise ValueError("region_name must be non-empty.")


class AwsSesTransport:
    """AWS SES v2 transport bound to an already-authorized CAP-007 execution."""

    provider_id = SES_PROVIDER_ID

    def __init__(self, *, config: AwsSesConfig, client_factory: Callable[..., Any] | None = None) -> None:
        self._config = config
        self._client_factory = client_factory or self._default_client_factory

    def send(self, *, message: EmailMessage, credentials: Mapping[str, str]) -> ProviderSendResult:
        try:
            client = self._client_factory(
                service_name="sesv2",
                region_name=self._config.region_name,
                aws_access_key_id=credentials["access_key_id"],
                aws_secret_access_key=credentials["secret_access_key"],
                aws_session_token=credentials.get("session_token") or None,
            )
            response = client.send_email(**self._request(message))
            message_id = str(response.get("MessageId", "")).strip()
            if not message_id:
                raise SesTransportError("SES returned no message identifier.")
            return ProviderSendResult(provider=self.provider_id, message_id=message_id, accepted=True)
        except SesTransportError:
            raise
        except Exception as exc:
            raise SesTransportError("AWS SES send failed.") from exc

    @staticmethod
    def _request(message: EmailMessage) -> dict[str, Any]:
        destination: dict[str, list[str]] = {"ToAddresses": list(message.to)}
        if message.cc:
            destination["CcAddresses"] = list(message.cc)
        if message.bcc:
            destination["BccAddresses"] = list(message.bcc)
        body: dict[str, Any] = {}
        if message.text_body is not None:
            body["Text"] = {"Data": message.text_body, "Charset": "UTF-8"}
        if message.html_body is not None:
            body["Html"] = {"Data": message.html_body, "Charset": "UTF-8"}
        request: dict[str, Any] = {
            "FromEmailAddress": message.sender,
            "Destination": destination,
            "Content": {"Simple": {"Subject": {"Data": message.subject, "Charset": "UTF-8"}, "Body": body}},
        }
        if message.reply_to:
            request["ReplyToAddresses"] = list(message.reply_to)
        return request

    @staticmethod
    def _default_client_factory(**kwargs: Any) -> Any:
        import boto3
        return boto3.client(**kwargs)
