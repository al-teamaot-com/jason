"""Governed Microsoft Graph client-credential access-token provider.

Secret material is resolved only at token acquisition time through an injected
secret provider. The token provider never persists the secret or access token and
is scoped to the Microsoft Graph application permission endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

import msal


class SecretValueProvider(Protocol):
    def get_secret(self, reference: str) -> str: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphClientCredentialConfig:
    tenant_id: str
    client_id: str
    client_secret_reference: str
    authority_host: str = "https://login.microsoftonline.com"
    scope: str = "https://graph.microsoft.com/.default"

    def validate(self) -> None:
        for name, value in {
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "client_secret_reference": self.client_secret_reference,
        }.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.authority_host.rstrip("/") != "https://login.microsoftonline.com":
            raise ValueError("only the canonical Microsoft authority host is approved")
        if self.scope != "https://graph.microsoft.com/.default":
            raise ValueError("Graph client credentials must use the .default scope")


@dataclass(frozen=True, slots=True)
class MicrosoftGraphClientCredentialTokenProvider:
    config: MicrosoftGraphClientCredentialConfig
    secrets: SecretValueProvider

    def access_token(self) -> str:
        self.config.validate()
        secret = self.secrets.get_secret(self.config.client_secret_reference)
        if not isinstance(secret, str) or not secret.strip():
            raise PermissionError("Microsoft Graph client credential secret is unavailable")

        authority = f"{self.config.authority_host.rstrip('/')}/{self.config.tenant_id.strip()}"
        application = msal.ConfidentialClientApplication(
            client_id=self.config.client_id.strip(),
            authority=authority,
            client_credential=secret,
        )
        result: Mapping[str, object] = application.acquire_token_for_client(
            scopes=[self.config.scope]
        )
        token = result.get("access_token")
        if not isinstance(token, str) or not token.strip():
            code = result.get("error")
            description = result.get("error_description")
            safe_code = code if isinstance(code, str) else "token_acquisition_failed"
            safe_description = description if isinstance(description, str) else ""
            # Microsoft error descriptions are bounded and should not contain the
            # client secret; never include the secret or token in exceptions.
            raise PermissionError(
                f"Microsoft Graph token acquisition failed: {safe_code}: {safe_description[:300]}"
            )
        return token.strip()
