from jason_mcp.provider_health_canary import _error_class


def test_denied_status_is_bounded_authority_error_class():
    assert (
        _error_class(
            status="denied",
            error_code=None,
            reason_codes=("IDENTITY_NOT_FOUND",),
        )
        == "authority_denied"
    )


def test_succeeded_status_is_none_error_class():
    assert (
        _error_class(
            status="succeeded",
            error_code=None,
            reason_codes=("capability_completed",),
        )
        == "none"
    )


def test_connector_authorization_denied_is_bounded_authority_error_class():
    assert (
        _error_class(
            status="failed",
            error_code="CONNECTOR_AUTHORIZATION_DENIED",
            reason_codes=("capability_invocation_failed",),
        )
        == "authority_denied"
    )


def test_unknown_provider_failure_is_sanitized_to_bounded_execution_failure():
    assert _error_class(
        status="failed",
        error_code="REMOTE_UNEXPECTED_BACKEND_CODE_UNKNOWN_4251",
        reason_codes=("invocation_failure",),
    ) == "execution_failed"


def test_empty_provider_failure_is_still_bounded_execution_failure():
    assert _error_class(status="failed", error_code=None, reason_codes=()) == "execution_failed"


def test_known_unavailability_and_timeout_classes_are_preserved():
    assert _error_class(status="failed", error_code="PROVIDER_UNAVAILABLE", reason_codes=()) == "provider_unavailable"
    assert _error_class(status="failed", error_code="TIMEOUT", reason_codes=()) == "timeout"
