from jason_mcp import server


def action():
    return {
        "capability": "automation.component.execute",
        "read_only": False,
        "action_enabled": True,
    }


def test_explicit_approval_bridges_from_arguments(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "_discoverable_capability",
        lambda name: action(),
    )

    captured = {}

    def governed_execute(
        *,
        capability_name,
        arguments,
        explicit_approval=False,
    ):
        captured["capability"] = capability_name
        captured["arguments"] = arguments
        captured["approval"] = explicit_approval
        return {"status": "succeeded"}

    monkeypatch.setattr(
        server,
        "_governed_execute",
        governed_execute,
    )

    result = server.execute_governed_capability(
        capability="automation.component.execute",
        arguments={
            "device_uid": "device-123",
            "component_name": "Example Component",
            "explicit_approval": True,
        },
    )

    assert result["status"] == "succeeded"
    assert captured["approval"] is True
    assert (
        "explicit_approval"
        not in captured["arguments"]
    )


def test_explicit_approval_defaults_false(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "_discoverable_capability",
        lambda name: action(),
    )

    captured = {}

    def governed_execute(
        *,
        capability_name,
        arguments,
        explicit_approval=False,
    ):
        captured["approval"] = explicit_approval
        return {"status": "approval_required"}

    monkeypatch.setattr(
        server,
        "_governed_execute",
        governed_execute,
    )

    server.execute_governed_capability(
        capability="automation.component.execute",
        arguments={
            "device_uid": "device-123",
            "component_name": "Example Component",
        },
    )

    assert captured["approval"] is False
