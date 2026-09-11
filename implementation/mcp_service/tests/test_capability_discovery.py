from jason_mcp import server


def _capability(
    name,
    operation,
    resource_types,
    *,
    display_name=None,
    fact_hints=None,
    canonical_facts=None,
):
    return {
        "capability": name,
        "display_name": display_name or name,
        "lifecycle": "active",
        "risk": "low",
        "read_only": True,
        "resource_types": list(resource_types),
        "operation": operation,
        "selector_keys": [],
        "fact_hints": list(fact_hints or []),
        "canonical_facts": list(canonical_facts or []),
        "input_schema": "test-input",
        "output_schema": "test-output",
        "approval_required": False,
        "tenant_isolation_required": True,
        "client_isolation_required": True,
    }


def test_exact_ticket_search_still_matches(monkeypatch):
    capabilities = [
        _capability(
            "service.ticket.search",
            "search",
            ["ticket"],
            display_name="Search service tickets",
            fact_hints=["ticket"],
        ),
    ]

    monkeypatch.setattr(
        server,
        "_discoverable_capabilities",
        lambda: capabilities,
    )

    result = server._filter_discoverable_capabilities(
        resource_type="ticket",
        operation="search",
    )

    assert result["capability_count"] == 1
    assert result["exact_filter_match"] is True
    assert result["capabilities"][0]["capability"] == "service.ticket.search"
    assert "alternatives" not in result


def test_read_word_does_not_hide_ticket_search_alternative(monkeypatch):
    capabilities = [
        _capability(
            "service.ticket.search",
            "search",
            ["ticket"],
            display_name="Search service tickets",
            fact_hints=["ticket", "ticket number"],
        ),
        _capability(
            "endpoint.device.read",
            "read",
            ["endpoint"],
            display_name="Read endpoint",
        ),
    ]

    monkeypatch.setattr(
        server,
        "_discoverable_capabilities",
        lambda: capabilities,
    )

    result = server._filter_discoverable_capabilities(
        resource_type="ticket",
        operation="read",
    )

    assert result["capability_count"] == 0
    assert result["exact_filter_match"] is False
    assert result["resource_capability_available"] is True
    assert result["alternative_count"] == 1
    assert [
        item["capability"]
        for item in result["alternatives"]
    ] == ["service.ticket.search"]
    assert "before concluding" in result["selection_guidance"]


def test_unknown_resource_remains_fail_closed(monkeypatch):
    capabilities = [
        _capability(
            "service.ticket.search",
            "search",
            ["ticket"],
        ),
    ]

    monkeypatch.setattr(
        server,
        "_discoverable_capabilities",
        lambda: capabilities,
    )

    result = server._filter_discoverable_capabilities(
        resource_type="not-registered",
        operation="read",
    )

    assert result["capability_count"] == 0
    assert result["resource_capability_available"] is False
    assert result["alternative_count"] == 0
    assert result["alternatives"] == []
