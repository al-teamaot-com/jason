from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote, urlencode, urlparse

from kernel.client_boundaries import SignedOnboardingState


_MICROSOFT_LOGIN_HOST = "login.microsoftonline.com"
_DEFAULT_GRAPH_SCOPE = "https://graph.microsoft.com/.default"

_DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$"
)


class MicrosoftConsentError(RuntimeError):
    """Safe Microsoft consent failure."""


class MicrosoftConsentDeniedError(MicrosoftConsentError):
    """The Microsoft tenant administrator denied consent."""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(
            f"Microsoft administrator consent failed: "
            f"{error_code}"
        )


class MicrosoftConsentValidationError(MicrosoftConsentError):
    """Microsoft consent callback validation failed."""


@dataclass(frozen=True)
class MicrosoftConsentConfiguration:
    application_id: str
    redirect_uri: str
    authority_host: str = _MICROSOFT_LOGIN_HOST
    graph_scope: str = _DEFAULT_GRAPH_SCOPE

    def __post_init__(self) -> None:
        _require_uuid(
            self.application_id,
            "application_id",
        )

        redirect = urlparse(self.redirect_uri)

        if (
            redirect.scheme != "https"
            or not redirect.netloc
            or redirect.fragment
        ):
            raise ValueError(
                "redirect_uri must be an absolute HTTPS URL "
                "without a fragment."
            )

        if self.authority_host != _MICROSOFT_LOGIN_HOST:
            raise ValueError(
                "Only the Microsoft public-cloud authority "
                "is approved for the first milestone."
            )

        if self.graph_scope != _DEFAULT_GRAPH_SCOPE:
            raise ValueError(
                "Only the Microsoft Graph .default scope "
                "is approved for the first milestone."
            )


@dataclass(frozen=True)
class MicrosoftAdminConsentRequest:
    url: str
    tenant_hint: str
    transaction_id: str
    expires_at_iso: str


@dataclass(frozen=True)
class MicrosoftAdminConsentResult:
    tenant_id: str
    state: str
    admin_consent: bool


def build_admin_consent_request(
    *,
    configuration: MicrosoftConsentConfiguration,
    tenant_hint: str,
    signed_state: SignedOnboardingState,
) -> MicrosoftAdminConsentRequest:
    normalized_tenant = _normalize_tenant_hint(
        tenant_hint
    )

    encoded_tenant = quote(
        normalized_tenant,
        safe="",
    )

    query = urlencode(
        {
            "client_id": configuration.application_id,
            "scope": configuration.graph_scope,
            "redirect_uri": configuration.redirect_uri,
            "state": signed_state.value,
        }
    )

    return MicrosoftAdminConsentRequest(
        url=(
            f"https://{configuration.authority_host}/"
            f"{encoded_tenant}/v2.0/adminconsent?{query}"
        ),
        tenant_hint=normalized_tenant,
        transaction_id=signed_state.transaction_id,
        expires_at_iso=signed_state.expires_at.isoformat(),
    )


def parse_admin_consent_callback(
    parameters: Mapping[str, str],
    *,
    expected_state: str,
) -> MicrosoftAdminConsentResult:
    returned_state = parameters.get("state")

    if not isinstance(returned_state, str):
        raise MicrosoftConsentValidationError(
            "Microsoft consent callback is missing state."
        )

    if not returned_state or returned_state != expected_state:
        raise MicrosoftConsentValidationError(
            "Microsoft consent callback state is invalid."
        )

    error_code = parameters.get("error")
    if error_code:
        safe_error = _safe_error_code(error_code)
        raise MicrosoftConsentDeniedError(safe_error)

    tenant_id = parameters.get("tenant")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise MicrosoftConsentValidationError(
            "Microsoft consent callback is missing tenant."
        )

    normalized_tenant_id = _require_uuid(
        tenant_id,
        "tenant",
    )

    admin_consent = parameters.get("admin_consent")

    if (
        not isinstance(admin_consent, str)
        or admin_consent.lower() != "true"
    ):
        raise MicrosoftConsentValidationError(
            "Microsoft administrator consent was not confirmed."
        )

    return MicrosoftAdminConsentResult(
        tenant_id=normalized_tenant_id,
        state=returned_state,
        admin_consent=True,
    )


def _normalize_tenant_hint(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "tenant_hint must be a verified domain "
            "or tenant UUID."
        )

    normalized = value.strip().lower()

    try:
        return str(uuid.UUID(normalized))
    except ValueError:
        pass

    if not _DOMAIN_PATTERN.fullmatch(normalized):
        raise ValueError(
            "tenant_hint must be a verified domain "
            "or tenant UUID."
        )

    return normalized


def _require_uuid(value: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(
            f"{field_name} must be a valid UUID."
        ) from error


def _safe_error_code(value: str) -> str:
    normalized = re.sub(
        r"[^A-Za-z0-9_.-]",
        "_",
        value,
    )[:100]

    return normalized or "MICROSOFT_CONSENT_DENIED"
