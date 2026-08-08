from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MicrosoftCredentialBinding:
    tenant_id: str
    client_id: str
    certificate_secret_name: str
    thumbprint_secret_name: str
    authority_host: str = "https://login.microsoftonline.com"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("tenant_id", self.tenant_id),
            ("client_id", self.client_id),
            ("certificate_secret_name", self.certificate_secret_name),
            ("thumbprint_secret_name", self.thumbprint_secret_name),
            ("authority_host", self.authority_host),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not self.certificate_secret_name.startswith("microsoft."):
            raise ValueError(
                "certificate_secret_name must use the microsoft.* logical-secret namespace"
            )
        if not self.thumbprint_secret_name.startswith("microsoft."):
            raise ValueError(
                "thumbprint_secret_name must use the microsoft.* logical-secret namespace"
            )
        if self.certificate_secret_name == self.thumbprint_secret_name:
            raise ValueError("certificate and thumbprint secret names must be distinct")
        if not self.authority_host.startswith("https://"):
            raise ValueError("authority_host must use HTTPS")
        if self.authority_host.rstrip("/") != "https://login.microsoftonline.com":
            raise ValueError("Only the canonical Microsoft authority host is approved")

    @property
    def authority(self) -> str:
        return f"{self.authority_host.rstrip('/')}/{self.tenant_id}"


@dataclass(frozen=True, slots=True)
class MicrosoftCredentialResolutionPlan:
    tenant_id: str
    client_id: str
    authority: str
    required_logical_secrets: tuple[str, str]


def build_credential_resolution_plan(
    binding: MicrosoftCredentialBinding,
) -> MicrosoftCredentialResolutionPlan:
    """Return a non-secret plan for the secrets broker.

    This function never reads a certificate, thumbprint, token, file, or network
    resource. The orchestrator/secrets broker resolves the named values later.
    """

    return MicrosoftCredentialResolutionPlan(
        tenant_id=binding.tenant_id,
        client_id=binding.client_id,
        authority=binding.authority,
        required_logical_secrets=(
            binding.certificate_secret_name,
            binding.thumbprint_secret_name,
        ),
    )
