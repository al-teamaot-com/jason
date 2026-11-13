from __future__ import annotations

import pytest

from connectors.core.openbao_secrets import (
    OpenBaoAuthenticationError, OpenBaoTransportError, OpenBaoHttpError,
    OpenBaoSecretResolutionError,
)
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.token import MicrosoftCredentialError


@pytest.mark.parametrize("error_class,expected", [
    (OpenBaoAuthenticationError, "MICROSOFT_CREDENTIAL_OPENBAO_AUTH_FAILED"),
    (OpenBaoTransportError, "MICROSOFT_CREDENTIAL_OPENBAO_UNREACHABLE"),
    (OpenBaoHttpError, "MICROSOFT_CREDENTIAL_OPENBAO_HTTP_ERROR"),
    (OpenBaoSecretResolutionError, "MICROSOFT_CREDENTIAL_RESOLUTION_FAILED"),
    (RuntimeError, "MICROSOFT_CREDENTIAL_RESOLUTION_FAILED"),
])
def test_credential_failure_reports_only_fixed_resolver_category(error_class, expected):
    class FailingSecrets:
        def resolve(self, *args):
            raise error_class("private-key-and-secret")

    with pytest.raises(MicrosoftCredentialError) as failure:
        OpenBaoMicrosoftCredentialSource(secrets=FailingSecrets()).resolve("fixture")
    assert failure.value.error_code == expected
    assert "private-key-and-secret" not in str(failure.value)


def test_upstream_http_status_remains_a_bounded_credential_category():
    class FailingSecrets:
        def resolve(self, *args):
            raise OpenBaoHttpError("private response body", status_code=403)

    with pytest.raises(MicrosoftCredentialError) as failure:
        OpenBaoMicrosoftCredentialSource(secrets=FailingSecrets()).resolve("fixture")
    assert failure.value.error_code == "MICROSOFT_CREDENTIAL_OPENBAO_HTTP_ERROR"
    assert "private response body" not in str(failure.value)
