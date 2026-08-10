from __future__ import annotations

from dataclasses import dataclass
from email.utils import parseaddr
from hashlib import sha256
from typing import Any, Mapping, Protocol, Sequence

from kernel.resolution import CapabilityResolutionResult
from orchestrator.contracts import OrchestrationRequest
from orchestrator.service import InvocationResult


CAPABILITY_NAME = "communication.email.send"
SES_PROVIDER_ID = "aws-ses"
SES_SECRET_NAME = "aws_ses.sendmail"

_PROHIBITED_ARGUMENTS = {
    "access_key_id",
    "secret_access_key",
    "session_token",
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
    "secret_path",
    "vault_path",
    "region",
    "aws_region",
    "endpoint_url",
}


class EmailCapabilityError(RuntimeError):
    error_code = "EMAIL_CAPABILITY_FAILED"


class EmailValidationError(EmailCapabilityError):
    error_code = "EMAIL_REQUEST_INVALID"


class EmailProviderMismatchError(EmailCapabilityError):
    error_code = "EMAIL_PROVIDER_MISMATCH"


class EmailSecretError(EmailCapabilityError):
    error_code = "EMAIL_SECRET_INVALID"


class EmailSenderDeniedError(EmailCapabilityError):
    error_code = "EMAIL_SENDER_DENIED"


@dataclass(frozen=True, slots=True)
class EmailMessage:
    sender: str
    to: tuple[str, ...]
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    reply_to: tuple[str, ...] = ()

    @property
    def recipient_count(self) -> int:
        return len(self.to) + len(self.cc) + len(self.bcc)


@dataclass(frozen=True, slots=True)
class SecretLease:
    values: Mapping[str, str]
    lease_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderSendResult:
    provider: str
    message_id: str
    accepted: bool = True


class SecretResolver(Protocol):
    def resolve(
        self,
        *,
        secret_name: str,
        purpose: str,
        execution_context_id: str,
        requester_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        correlation_id: str,
    ) -> SecretLease: ...

    def revoke(self, lease: SecretLease) -> None: ...


class EmailTransport(Protocol):
    provider_id: str

    def send(self, *, message: EmailMessage, credentials: Mapping[str, str]) -> ProviderSendResult: ...


@dataclass(frozen=True, slots=True)
class EmailSendPolicy:
    default_sender: str
    allowed_senders: tuple[str, ...] = ()
    allow_bcc: bool = False
    max_recipients: int = 25

    def sender_allowed(self, sender: str) -> bool:
        allowed = {self.default_sender.casefold(), *(item.casefold() for item in self.allowed_senders)}
        return sender.casefold() in allowed


class GovernedEmailSendInvoker:
    """Orchestrator-compatible CAP-004 invoker.

    Authority, approval, capability resolution, provider selection, and policy
    decisions occur before this invoker is called. This class validates the
    canonical message, resolves only the named SES secret through JKD-003, and
    invokes the already selected provider transport.
    """

    def __init__(
        self,
        *,
        secrets: SecretResolver,
        transport: EmailTransport,
        policy: EmailSendPolicy,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._policy = policy

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if request.capability_name != CAPABILITY_NAME or resolution.capability_name != CAPABILITY_NAME:
            raise EmailValidationError("CAP-004 received an unexpected capability name.")
        if resolution.selected_provider_id != self._transport.provider_id:
            raise EmailProviderMismatchError("Resolved provider does not match the bound email transport.")
        if self._transport.provider_id != SES_PROVIDER_ID:
            raise EmailProviderMismatchError("CAP-004 SES invoker is bound to an unexpected provider.")

        message = self._message_from_arguments(request.arguments)
        lease: SecretLease | None = None
        try:
            lease = self._secrets.resolve(
                secret_name=SES_SECRET_NAME,
                purpose="send governed email through AWS SES",
                execution_context_id=request.execution_id,
                requester_id=request.principal_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                capability=CAPABILITY_NAME,
                correlation_id=request.correlation_id,
            )
            credentials = self._validate_secret(lease.values)
            result = self._transport.send(message=message, credentials=credentials)
        finally:
            if lease is not None:
                self._secrets.revoke(lease)

        if result.provider != self._transport.provider_id:
            raise EmailProviderMismatchError("Transport returned an unexpected provider identity.")
        if not result.accepted:
            raise EmailCapabilityError("Email provider did not accept the message.")

        return InvocationResult(
            output={
                "provider": result.provider,
                "message_id": result.message_id,
                "accepted": result.accepted,
                "recipient_count": message.recipient_count,
                "subject_sha256": sha256(message.subject.encode("utf-8")).hexdigest(),
            },
            attempts=1,
        )

    def _message_from_arguments(self, arguments: Mapping[str, Any]) -> EmailMessage:
        prohibited = sorted(_PROHIBITED_ARGUMENTS.intersection(arguments))
        if prohibited:
            raise EmailValidationError(
                "Provider credentials or configuration are prohibited request arguments: "
                + ", ".join(prohibited)
            )

        to = self._addresses(arguments.get("to"), "to", required=True)
        cc = self._addresses(arguments.get("cc"), "cc")
        bcc = self._addresses(arguments.get("bcc"), "bcc")
        reply_to = self._addresses(arguments.get("reply_to"), "reply_to")

        if bcc and not self._policy.allow_bcc:
            raise EmailValidationError("BCC is not permitted by the active CAP-004 policy.")

        subject = str(arguments.get("subject", "")).strip()
        if not subject:
            raise EmailValidationError("subject must be non-empty.")

        text_body = self._optional_body(arguments.get("text_body"))
        html_body = self._optional_body(arguments.get("html_body"))
        if text_body is None and html_body is None:
            raise EmailValidationError("At least one of text_body or html_body is required.")

        requested_sender = str(arguments.get("from_address", "")).strip()
        sender = requested_sender or self._policy.default_sender
        self._validate_address(sender, "from_address")
        if not self._policy.sender_allowed(sender):
            raise EmailSenderDeniedError("Requested sender is not allowed by CAP-004 policy.")

        count = len(to) + len(cc) + len(bcc)
        if count > self._policy.max_recipients:
            raise EmailValidationError("Recipient count exceeds the CAP-004 policy limit.")

        return EmailMessage(
            sender=sender,
            to=to,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
        )

    @staticmethod
    def _optional_body(value: Any) -> str | None:
        if value is None:
            return None
        rendered = str(value)
        return rendered if rendered.strip() else None

    def _addresses(self, value: Any, field_name: str, *, required: bool = False) -> tuple[str, ...]:
        if value is None:
            items: Sequence[Any] = ()
        elif isinstance(value, str):
            items = (value,)
        elif isinstance(value, Sequence):
            items = value
        else:
            raise EmailValidationError(f"{field_name} must be a string or sequence of strings.")

        addresses = tuple(str(item).strip() for item in items if str(item).strip())
        if required and not addresses:
            raise EmailValidationError(f"{field_name} requires at least one address.")
        for address in addresses:
            self._validate_address(address, field_name)
        return addresses

    @staticmethod
    def _validate_address(address: str, field_name: str) -> None:
        _, parsed = parseaddr(address)
        if parsed != address or "@" not in parsed or parsed.startswith("@") or parsed.endswith("@"):
            raise EmailValidationError(f"{field_name} contains a malformed email address.")

    @staticmethod
    def _validate_secret(values: Mapping[str, str]) -> Mapping[str, str]:
        required = {"access_key_id", "secret_access_key"}
        missing = sorted(name for name in required if not str(values.get(name, "")).strip())
        allowed = required | {"session_token"}
        unexpected = sorted(set(values) - allowed)
        if missing or unexpected:
            raise EmailSecretError("SES secret payload does not match the approved CAP-004 schema.")
        return dict(values)
