from types import SimpleNamespace

from jason_mcp import server


def test_discovery_includes_active_reads_and_explicit_actions(monkeypatch):
    def capability(
        name,
        *,
        read_only,
        write_capability=False,
        action_enabled=False,
    ):
        return SimpleNamespace(
            capability_name=name,
            display_name=name,
            lifecycle_status=SimpleNamespace(value="active"),
            risk_level=SimpleNamespace(value="high" if write_capability else "low"),
            metadata={
                "read_only": "true" if read_only else "false",
                "write_capability": "true" if write_capability else "false",
                "mcp_action_enabled": "true" if action_enabled else "false",
                "resource_types": "service.ticket",
                "operation": "create" if write_capability else "search",
            },
            input_schema_reference="schema://input",
            output_schema_reference="schema://output",
            approval=SimpleNamespace(required=write_capability),
            tenant_isolation_required=True,
            client_isolation_required=True,
        )

    capabilities = SimpleNamespace(
        list_all=lambda: [
            capability(
                "service.ticket.search",
                read_only=True,
            ),
            capability(
                "service.ticket.note.create",
                read_only=False,
                write_capability=True,
                action_enabled=True,
            ),
            capability(
                "service.ticket.update.hidden",
                read_only=False,
                write_capability=True,
                action_enabled=False,
            ),
        ]
    )

    monkeypatch.setattr(
        server,
        "_runtime",
        lambda: SimpleNamespace(capabilities=capabilities),
    )

    discovered = server._discoverable_capabilities()
    names = [item["capability"] for item in discovered]

    assert names == [
        "service.ticket.note.create",
        "service.ticket.search",
    ]

    action = next(
        item
        for item in discovered
        if item["capability"] == "service.ticket.note.create"
    )

    assert action["classification"] == "action"
    assert action["write_capability"] is True
    assert action["action_enabled"] is True


def test_generic_execution_dispatches_read(monkeypatch):
    monkeypatch.setattr(
        server,
        "_discoverable_capability",
        lambda name: {
            "capability": name,
            "read_only": True,
            "action_enabled": False,
        },
    )

    captured = {}

    def execute_read_capability(*, capability, arguments):
        captured["capability"] = capability
        captured["arguments"] = arguments
        return {"status": "succeeded"}

    monkeypatch.setattr(
        server,
        "execute_read_capability",
        execute_read_capability,
    )

    result = server.execute_governed_capability(
        capability="endpoint.device.read",
        arguments={"resource_id": "example"},
    )

    assert result["status"] == "succeeded"
    assert captured == {
        "capability": "endpoint.device.read",
        "arguments": {"resource_id": "example"},
    }


def test_generic_execution_dispatches_explicit_action(monkeypatch):
    monkeypatch.setattr(
        server,
        "_discoverable_capability",
        lambda name: {
            "capability": name,
            "read_only": False,
            "action_enabled": True,
        },
    )

    captured = {}

    def governed_execute(*, capability_name, arguments):
        captured["capability"] = capability_name
        captured["arguments"] = arguments
        return {"status": "succeeded"}

    monkeypatch.setattr(
        server,
        "_governed_execute",
        governed_execute,
    )

    result = server.execute_governed_capability(
        capability="service.ticket.note.create",
        arguments={
            "payload": {
                "ticketID": 123,
                "description": "test",
                "noteType": 3,
                "publish": 1,
            }
        },
    )

    assert result["status"] == "succeeded"
    assert captured["capability"] == "service.ticket.note.create"


def test_generic_execution_rejects_unexposed_capability(monkeypatch):
    monkeypatch.setattr(
        server,
        "_discoverable_capability",
        lambda name: None,
    )

    result = server.execute_governed_capability(
        capability="service.ticket.delete",
        arguments={},
    )

    assert result == {
        "status": "rejected",
        "capability": "service.ticket.delete",
        "error_code": "capability_not_active_or_exposed",
    }


def test_status_reports_all_active_actions(monkeypatch):
    monkeypatch.setattr(
        server,
        "_active_action_capabilities",
        lambda: [
            "automation.component.execute",
            "service.ticket.note.create",
            "service.ticket.update",
        ],
    )

    result = server.jason_mcp_status()

    assert result["mode"] == "governed-read-plus-actions"
    assert result["phase"] == "governed-action-pilot"
    assert result["write_tools_enabled"] is True
    assert result["write_capabilities"] == [
        "automation.component.execute",
        "service.ticket.note.create",
        "service.ticket.update",
    ]


def test_discovery_reports_requester_potential_eligibility(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "_filter_discoverable_capabilities",
        lambda **kwargs: {
            "status": "succeeded",
            "capability_count": 2,
            "capabilities": [
                {
                    "capability": "endpoint.device.read",
                    "read_only": True,
                },
                {
                    "capability": "service.ticket.update",
                    "read_only": False,
                },
            ],
        },
    )

    monkeypatch.setattr(
        server,
        "_authenticated_identity",
        lambda: (
            "person-al",
            "aot",
            "entra-oauth-bearer",
            None,
        ),
    )

    class Authority:
        def evaluate(self, request):
            if request.capability == "endpoint.device.read":
                outcome = server.AuthorityOutcome.ALLOWED
            else:
                outcome = (
                    server.AuthorityOutcome.APPROVAL_REQUIRED
                )

            return SimpleNamespace(
                outcome=outcome,
            )

    monkeypatch.setattr(
        server,
        "_runtime",
        lambda: SimpleNamespace(
            identity_authority=Authority(),
        ),
    )

    result = server.discover_capabilities()

    read = result["capabilities"][0]
    action = result["capabilities"][1]

    assert read["permission_mode"] == "observe"
    assert read["potentially_eligible"] is True
    assert read["authority_outcome"] == "allowed"

    assert action["permission_mode"] == "execute"
    assert action["potentially_eligible"] is True
    assert action["authority_outcome"] == "approval_required"


def test_discovery_marks_denied_requester_ineligible(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "_filter_discoverable_capabilities",
        lambda **kwargs: {
            "status": "succeeded",
            "capability_count": 1,
            "capabilities": [
                {
                    "capability": "service.ticket.update",
                    "read_only": False,
                },
            ],
        },
    )

    monkeypatch.setattr(
        server,
        "_authenticated_identity",
        lambda: (
            "person-readonly",
            "aot",
            "entra-oauth-bearer",
            None,
        ),
    )

    class Authority:
        def evaluate(self, request):
            return SimpleNamespace(
                outcome=server.AuthorityOutcome.DENIED,
            )

    monkeypatch.setattr(
        server,
        "_runtime",
        lambda: SimpleNamespace(
            identity_authority=Authority(),
        ),
    )

    result = server.discover_capabilities()

    action = result["capabilities"][0]

    assert action["permission_mode"] == "execute"
    assert action["potentially_eligible"] is False
    assert action["authority_outcome"] == "denied"


def test_ticket_update_action_result_is_verification_only():
    result = server._project_action_result(
        "service.ticket.update",
        {
            "data": {
                "id": 123,
                "providerRawObject": {
                    "sensitive": "must-not-escape",
                },
                "jasonVerification": {
                    "readbackVerified": True,
                    "ticketId": 123,
                    "verifiedFields": [
                        "status",
                        "priority",
                    ],
                },
            },
        },
    )

    assert result == {
        "raw_provider_evidence_exposed": False,
        "verification_available": True,
        "readback_verified": True,
        "ticket_id": 123,
        "verified_fields": [
            "status",
            "priority",
        ],
        "verified_fields_bounded": False,
    }

    assert "providerRawObject" not in result


def test_internal_note_action_result_omits_resource_attribution():
    result = server._project_action_result(
        "service.ticket.note.create",
        {
            "data": {
                "providerPayload": "must-not-escape",
                "jasonVerification": {
                    "readbackVerified": True,
                    "ticketNoteId": 456,
                    "creatorResourceId": 987654,
                    "impersonatorRecorded": True,
                },
            },
        },
    )

    assert result == {
        "raw_provider_evidence_exposed": False,
        "verification_available": True,
        "readback_verified": True,
        "ticket_note_id": 456,
        "impersonator_recorded": True,
    }

    assert "creatorResourceId" not in result
    assert "providerPayload" not in result


def test_datto_action_result_exposes_governed_job_uid_for_readback():
    result = server._project_action_result(
        "automation.component.execute",
        {
            "data": {
                "status": "accepted",
                "job_uid": "provider-job-123",
                "job_status": "active",
                "readback_verified": True,
                "completion_verified": False,
                "allowlist_name": "diagnostic",
                "unexpected": "must-not-escape",
            },
        },
    )

    assert result == {
        "raw_provider_evidence_exposed": False,
        "status": "accepted",
        "job_status": "active",
        "readback_verified": True,
        "completion_verified": False,
        "allowlist_name": "diagnostic",
        "job_uid": "provider-job-123",
        "job_reference_present": True,
    }

    assert "unexpected" not in result


def test_unknown_action_result_fails_closed():
    result = server._project_action_result(
        "future.unknown.action",
        {
            "data": {
                "arbitrary": "must-not-escape",
            },
        },
    )

    assert result == {
        "raw_provider_evidence_exposed": False,
        "result_exposed": False,
    }
