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
