import pytest

from jason_mcp import server


def test_internal_note_payload_fixes_internal_visibility():
    arguments = server._internal_note_arguments(
        ticket_id=12345,
        note="Technician-only validation note",
        title="Jason internal note",
    )

    assert arguments == {
        "payload": {
            "ticketID": 12345,
            "description": "Technician-only validation note",
            "noteType": 3,
            "publish": 1,
            "title": "Jason internal note",
        }
    }


@pytest.mark.parametrize(
    ("ticket_id", "note"),
    [
        (0, "note"),
        (-1, "note"),
        (1, ""),
        (1, "   "),
    ],
)
def test_internal_note_payload_rejects_invalid_input(
    ticket_id,
    note,
):
    with pytest.raises(
        ValueError
    ):
        server._internal_note_arguments(
            ticket_id=ticket_id,
            note=note,
        )


def test_owner_organization_scope_reaches_exact_authority(
    monkeypatch,
):
    class _Capability:
        metadata = {
            "mcp_action_enabled": "true",
        }

    class _Capabilities:
        def get_current(
            self,
            *,
            capability_name,
        ):
            assert (
                capability_name
                == "service.ticket.note.create"
            )

            return _Capability()

    class _Decision:
        outcome = server.AuthorityOutcome.DENIED
        reason_codes = (
            "TEST_EXACT_AUTHORITY_DENY",
        )

    class _Authority:
        def __init__(self):
            self.request = None

        def evaluate(
            self,
            request,
        ):
            self.request = request
            return _Decision()

    authority = _Authority()

    class _App:
        identity_authority = authority
        capabilities = _Capabilities()

    monkeypatch.setattr(
        server,
        "autotask_internal_note_mcp_surface_enabled",
        lambda: True,
    )

    monkeypatch.setattr(
        server,
        "_runtime",
        lambda: _App(),
    )

    monkeypatch.setattr(
        server,
        "_authenticated_write_identity",
        lambda: (
            "person-al",
            "aot",
            "entra-oauth-bearer",
            None,
        ),
    )

    result = server._governed_internal_note_create(
        ticket_id=12345,
        note="Must reach exact Jason authority.",
    )

    assert result[
        "status"
    ] == "denied"

    assert result[
        "reason_codes"
    ] == [
        "TEST_EXACT_AUTHORITY_DENY",
    ]

    assert authority.request is not None
    assert authority.request.client_id is None

    assert (
        authority.request.requested_mode
        is server.PermissionMode.EXECUTE
    )

    assert (
        authority.request.capability
        == "service.ticket.note.create"
    )
