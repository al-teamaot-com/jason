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
