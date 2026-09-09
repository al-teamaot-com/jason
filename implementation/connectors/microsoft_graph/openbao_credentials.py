from __future__ import annotations

from dataclasses import dataclass

from connectors.core.contracts import ConnectorContext, SecretResolver

from .token import MicrosoftCertificateCredential, MicrosoftCredentialError


@dataclass(frozen=True, slots=True)
class OpenBaoMicrosoftCredentialSource:
    """Adapt Jason's governed secret resolver to Microsoft certificate credentials.

    Secret material remains inside the resolver/provider boundary and is returned only
    as the bounded credential object required by the MSAL token provider. No environment
    or filesystem fallback is permitted here.
    """

    secrets: SecretResolver
    organization_id: str = "aot"
    principal_id: str = "microsoft-graph-token-provider"

    def resolve(self, logical_secret: str) -> MicrosoftCertificateCredential:
        if not logical_secret.strip():
            raise MicrosoftCredentialError(
                error_code="MICROSOFT_LOGICAL_SECRET_INVALID",
                message="Microsoft logical secret is invalid.",
            )
        context = ConnectorContext(
            correlation_id=f"microsoft-credential:{logical_secret}",
            principal_id=self.principal_id,
            organization_id=self.organization_id,
            client_id=None,
            capability="microsoft_graph.token.acquire",
            mode="observe",
        )
        try:
            values = self.secrets.resolve(logical_secret, context)
            return MicrosoftCertificateCredential(
                private_key_pem=str(values["private_key_pem"]),
                certificate_pem=str(values["certificate_pem"]),
                certificate_thumbprint=str(values["certificate_thumbprint"]),
                generation=str(values["generation"]),
            )
        except MicrosoftCredentialError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise MicrosoftCredentialError(
                error_code="MICROSOFT_CREDENTIAL_CONTRACT_INVALID",
                message="Microsoft application credential contract is invalid.",
            ) from error
        except Exception as error:
            raise MicrosoftCredentialError(
                error_code="MICROSOFT_CREDENTIAL_RESOLUTION_FAILED",
                message="Microsoft application credential could not be resolved.",
            ) from error
