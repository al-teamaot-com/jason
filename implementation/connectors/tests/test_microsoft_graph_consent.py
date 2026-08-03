from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from connectors.microsoft_graph import (
    MicrosoftConsentConfiguration,
    MicrosoftConsentDeniedError,
    MicrosoftConsentValidationError,
    build_admin_consent_request,
    parse_admin_consent_callback,
)
from kernel.client_boundaries import SignedOnboardingState


APPLICATION_ID = "11111111-2222-3333-4444-555555555555"
TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

EXPIRES_AT = datetime(
    2026,
    8,
    3,
    20,
    0,
    tzinfo=timezone.utc,
)


def build_configuration() -> MicrosoftConsentConfiguration:
    return MicrosoftConsentConfiguration(
        application_id=APPLICATION_ID,
        redirect_uri=(
            "https://jason.example.test/"
            "microsoft/admin-consent/callback"
        ),
    )


def build_state() -> SignedOnboardingState:
    return SignedOnboardingState(
        value="signed.kernel.state",
        transaction_id="txn_001",
        expires_at=EXPIRES_AT,
    )


def test_builds_tenant_specific_admin_consent_url() -> None:
    request = build_admin_consent_request(
        configuration=build_configuration(),
        tenant_hint="FaithFormation.org",
        signed_state=build_state(),
    )

    parsed = urlparse(request.url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == (
        "/faithformation.org/v2.0/adminconsent"
    )
    assert query == {
        "client_id": [APPLICATION_ID],
        "scope": [
            "https://graph.microsoft.com/.default"
        ],
        "redirect_uri": [
            "https://jason.example.test/"
            "microsoft/admin-consent/callback"
        ],
        "state": ["signed.kernel.state"],
    }
    assert request.transaction_id == "txn_001"
    assert request.tenant_hint == "faithformation.org"


def test_accepts_tenant_uuid_as_hint() -> None:
    request = build_admin_consent_request(
        configuration=build_configuration(),
        tenant_hint=TENANT_ID.upper(),
        signed_state=build_state(),
    )

    assert (
        f"/{TENANT_ID}/v2.0/adminconsent"
        in request.url
    )


@pytest.mark.parametrize(
    "tenant_hint",
    [
        "",
        "organizations",
        "common",
        "not a domain",
        "-invalid.example",
        "localhost",
    ],
)
def test_rejects_unapproved_tenant_hint(
    tenant_hint: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="verified domain or tenant UUID",
    ):
        build_admin_consent_request(
            configuration=build_configuration(),
            tenant_hint=tenant_hint,
            signed_state=build_state(),
        )


def test_parses_successful_admin_consent_callback() -> None:
    result = parse_admin_consent_callback(
        {
            "tenant": TENANT_ID.upper(),
            "state": "signed.kernel.state",
            "admin_consent": "True",
        },
        expected_state="signed.kernel.state",
    )

    assert result.tenant_id == TENANT_ID
    assert result.state == "signed.kernel.state"
    assert result.admin_consent is True


def test_rejects_missing_state() -> None:
    with pytest.raises(
        MicrosoftConsentValidationError,
        match="missing state",
    ):
        parse_admin_consent_callback(
            {
                "tenant": TENANT_ID,
                "admin_consent": "True",
            },
            expected_state="signed.kernel.state",
        )


def test_rejects_mismatched_state() -> None:
    with pytest.raises(
        MicrosoftConsentValidationError,
        match="state is invalid",
    ):
        parse_admin_consent_callback(
            {
                "tenant": TENANT_ID,
                "state": "different.state",
                "admin_consent": "True",
            },
            expected_state="signed.kernel.state",
        )


def test_reports_safe_consent_denial() -> None:
    with pytest.raises(
        MicrosoftConsentDeniedError,
        match="permission_denied",
    ) as captured:
        parse_admin_consent_callback(
            {
                "state": "signed.kernel.state",
                "error": "permission_denied",
                "error_description": (
                    "The administrator cancelled."
                ),
            },
            expected_state="signed.kernel.state",
        )

    assert captured.value.error_code == (
        "permission_denied"
    )
    assert "cancelled" not in str(captured.value)


def test_sanitizes_provider_error_code() -> None:
    with pytest.raises(
        MicrosoftConsentDeniedError,
    ) as captured:
        parse_admin_consent_callback(
            {
                "state": "signed.kernel.state",
                "error": "bad error<script>",
            },
            expected_state="signed.kernel.state",
        )

    assert captured.value.error_code == (
        "bad_error_script_"
    )


def test_rejects_missing_tenant() -> None:
    with pytest.raises(
        MicrosoftConsentValidationError,
        match="missing tenant",
    ):
        parse_admin_consent_callback(
            {
                "state": "signed.kernel.state",
                "admin_consent": "True",
            },
            expected_state="signed.kernel.state",
        )


def test_rejects_invalid_tenant_uuid() -> None:
    with pytest.raises(
        ValueError,
        match="tenant must be a valid UUID",
    ):
        parse_admin_consent_callback(
            {
                "tenant": "not-a-uuid",
                "state": "signed.kernel.state",
                "admin_consent": "True",
            },
            expected_state="signed.kernel.state",
        )


def test_rejects_unconfirmed_admin_consent() -> None:
    with pytest.raises(
        MicrosoftConsentValidationError,
        match="was not confirmed",
    ):
        parse_admin_consent_callback(
            {
                "tenant": TENANT_ID,
                "state": "signed.kernel.state",
                "admin_consent": "False",
            },
            expected_state="signed.kernel.state",
        )


@pytest.mark.parametrize(
    "application_id",
    [
        "",
        "not-a-uuid",
    ],
)
def test_rejects_invalid_application_id(
    application_id: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="application_id",
    ):
        MicrosoftConsentConfiguration(
            application_id=application_id,
            redirect_uri=(
                "https://jason.example.test/callback"
            ),
        )


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://jason.example.test/callback",
        "https:///missing-host",
        "https://jason.example.test/callback#fragment",
        "not-a-url",
    ],
)
def test_rejects_invalid_redirect_uri(
    redirect_uri: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="absolute HTTPS URL",
    ):
        MicrosoftConsentConfiguration(
            application_id=APPLICATION_ID,
            redirect_uri=redirect_uri,
        )


def test_rejects_unapproved_authority_host() -> None:
    with pytest.raises(
        ValueError,
        match="public-cloud authority",
    ):
        MicrosoftConsentConfiguration(
            application_id=APPLICATION_ID,
            redirect_uri=(
                "https://jason.example.test/callback"
            ),
            authority_host="login.example.test",
        )


def test_rejects_non_default_graph_scope() -> None:
    with pytest.raises(
        ValueError,
        match=r"Graph \.default scope",
    ):
        MicrosoftConsentConfiguration(
            application_id=APPLICATION_ID,
            redirect_uri=(
                "https://jason.example.test/callback"
            ),
            graph_scope="User.Read.All",
        )
