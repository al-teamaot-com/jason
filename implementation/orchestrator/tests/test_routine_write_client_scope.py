import pytest

from orchestrator.routine_write_client_scope import resolve_routine_write_client


@pytest.mark.parametrize("capability", (
    "identity.user.create", "documentation.configuration.update",
))
def test_aot_technician_selects_exact_client_without_inheriting_authority(capability):
    client, arguments = resolve_routine_write_client(
        capability=capability,
        authenticated_client_id=None,
        arguments={"client_id": "XYZ-1158", "target": "approved"},
    )
    assert client == "XYZ-1158"
    assert arguments == {"target": "approved"}


@pytest.mark.parametrize("invalid", (
    None, "", " ", "*", "client*", "x?y", "x[1]", "../client",
    "ABC client", 12, False, "A"*129, " xyz ", "xyz\nother",
))
def test_invalid_client_scope_is_rejected_before_authority(invalid):
    with pytest.raises(ValueError, match="EXACT_CLIENT_ID_REQUIRED"):
        resolve_routine_write_client(
            capability="identity.user.create",
            authenticated_client_id=None,
            arguments={"client_id": invalid, "user_principal_name": "u@xyz.test"},
        )


def test_authenticated_client_binding_cannot_be_overridden():
    with pytest.raises(PermissionError, match="SCOPE_MISMATCH"):
        resolve_routine_write_client(
            capability="documentation.configuration.update",
            authenticated_client_id="XYZ",
            arguments={"client_id": "RIGGINS", "configuration_id": 14},
        )


def test_matching_bound_client_allowed():
    client, args = resolve_routine_write_client(
        capability="identity.user.create",
        authenticated_client_id="XYZ",
        arguments={"client_id": "XYZ", "onboarding_request_id": "REQ-2"},
    )
    assert client == "XYZ" and args == {"onboarding_request_id": "REQ-2"}


def test_other_actions_not_changed_or_reinterpreted():
    payload = {"client_id": "unrelated", "ticket_id": 123}
    client, args = resolve_routine_write_client(
        capability="service.ticket.update",
        authenticated_client_id=None,
        arguments=payload,
    )
    assert client is None and args == payload
