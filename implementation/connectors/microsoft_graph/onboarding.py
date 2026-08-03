from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from connectors.microsoft_graph.consent import (
    MicrosoftAdminConsentRequest,
    MicrosoftAdminConsentResult,
    MicrosoftConsentConfiguration,
    build_admin_consent_request,
    parse_admin_consent_callback,
)
from kernel.client_boundaries import (
    ClientBoundary,
    ClientBoundaryService,
    OnboardingTransaction,
)


@dataclass(frozen=True)
class MicrosoftOnboardingSession:
    transaction: OnboardingTransaction
    consent_request: MicrosoftAdminConsentRequest
    signed_state: str


@dataclass(frozen=True)
class MicrosoftOnboardingCompletion:
    consent_result: MicrosoftAdminConsentResult
    boundary: ClientBoundary


class MicrosoftOnboardingOrchestrator:
    def __init__(
        self,
        *,
        configuration: MicrosoftConsentConfiguration,
        boundaries: ClientBoundaryService,
        provider_name: str = "microsoft_graph",
        profile_name: str = "directory-read",
    ) -> None:
        if not provider_name.strip():
            raise ValueError(
                "provider_name must be a non-empty string."
            )

        if not profile_name.strip():
            raise ValueError(
                "profile_name must be a non-empty string."
            )

        self._configuration = configuration
        self._boundaries = boundaries
        self._provider_name = provider_name
        self._profile_name = profile_name

    def begin(
        self,
        *,
        client_id: str,
        primary_domain: str,
        correlation_id: str,
        lifetime: timedelta = timedelta(minutes=15),
    ) -> MicrosoftOnboardingSession:
        transaction, signed_state = (
            self._boundaries.begin_onboarding(
                client_id=client_id,
                provider=self._provider_name,
                primary_domain=primary_domain,
                profile=self._profile_name,
                application_id=(
                    self._configuration.application_id
                ),
                correlation_id=correlation_id,
                lifetime=lifetime,
            )
        )

        consent_request = build_admin_consent_request(
            configuration=self._configuration,
            tenant_hint=transaction.primary_domain,
            signed_state=signed_state,
        )

        return MicrosoftOnboardingSession(
            transaction=transaction,
            consent_request=consent_request,
            signed_state=signed_state.value,
        )

    def complete(
        self,
        *,
        callback_parameters: Mapping[str, str],
        expected_state: str,
        consented_at: datetime,
        service_principal_id: str | None = None,
    ) -> MicrosoftOnboardingCompletion:
        consent_result = parse_admin_consent_callback(
            callback_parameters,
            expected_state=expected_state,
        )

        boundary = self._boundaries.complete_onboarding(
            state=consent_result.state,
            external_tenant_id=consent_result.tenant_id,
            consented_at=consented_at,
            service_principal_id=service_principal_id,
        )

        if (
            boundary.application_id
            != self._configuration.application_id
        ):
            raise RuntimeError(
                "Completed boundary uses an unexpected "
                "Microsoft application."
            )

        if boundary.provider != self._provider_name:
            raise RuntimeError(
                "Completed boundary uses an unexpected provider."
            )

        if boundary.profile != self._profile_name:
            raise RuntimeError(
                "Completed boundary uses an unexpected profile."
            )

        return MicrosoftOnboardingCompletion(
            consent_result=consent_result,
            boundary=boundary,
        )
