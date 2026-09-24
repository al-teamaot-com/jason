from types import SimpleNamespace

import pytest

from jason_mcp import server


def _ticket(*, ticket_id=123, configuration_id=None, title="Alert for DEVICE-123"):
    return {
        "id": ticket_id,
        "queueID": 29682833,
        "status": 1,
        "companyID": 99,
        "configurationItemID": configuration_id,
        "issueType": None,
        "title": title,
    }


def _ticket_read(record):
    return {
        "status": "succeeded",
        "evidence": {"data": {"items": [record]}},
    }


def test_triage_does_not_qualify_as_substantive_work(monkeypatch):
    monkeypatch.setattr(
        server,
        "_governed_read",
        lambda **kwargs: _ticket_read(_ticket(title="Generic ticket")),
    )
    with pytest.raises(ValueError, match="SUBSTANTIVE_ACTION_REQUIRED"):
        server._canonicalize_governed_action_arguments(
            "service.ticket.update",
            {"ticket_id": 123, "begin_work": True, "work_kind": "triage"},
        )


def test_endpoint_claim_requires_authoritative_online_read(monkeypatch):
    calls = []

    def governed_read(*, capability_name, arguments):
        calls.append((capability_name, dict(arguments)))
        if capability_name == "service.ticket.read":
            return _ticket_read(_ticket())
        if capability_name == "endpoint.device.search":
            return {
                "status": "succeeded",
                "evidence": {
                    "resource_matches": [{
                        "resource_id": "device-uid-123",
                        "hostname": "DEVICE-123",
                    }]
                },
            }
        if capability_name == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "device-uid-123",
                        "hostname": "DEVICE-123",
                        "online": False,
                        "suspended": False,
                        "deleted": False,
                    }
                },
            }
        raise AssertionError(capability_name)

    monkeypatch.setattr(server, "_governed_read", governed_read)
    with pytest.raises(ValueError, match="DEVICE_OFFLINE"):
        server._canonicalize_governed_action_arguments(
            "service.ticket.update",
            {"ticket_id": 123, "begin_work": True, "work_kind": "diagnostic"},
        )
    assert [name for name, _ in calls] == [
        "service.ticket.read",
        "endpoint.device.search",
        "endpoint.device.read",
    ]


def test_start_captures_original_queue_and_status(monkeypatch):
    def governed_read(*, capability_name, arguments):
        if capability_name == "service.ticket.read":
            return _ticket_read(_ticket(title="Generic ticket"))
        raise AssertionError(capability_name)

    monkeypatch.setattr(server, "_governed_read", governed_read)
    monkeypatch.setattr(
        server,
        "_ticket_work_claim_store",
        lambda: SimpleNamespace(get=lambda ticket_id: None),
    )

    result = server._canonicalize_governed_action_arguments(
        "service.ticket.update",
        {"ticket_id": 123, "begin_work": True, "work_kind": "diagnostic"},
    )
    assert result["payload"]["queueID"] == "Jason"
    assert result["payload"]["status"] == "In Progress"
    assert result["jason_original_queue_id"] == 29682833
    assert result["jason_original_status_id"] == 1


def test_handoff_restores_only_trusted_preclaim_state(monkeypatch):
    claim = SimpleNamespace(
        state="claimed",
        original_queue_id=29682833,
        original_status_id=1,
    )
    monkeypatch.setattr(
        server,
        "_ticket_work_claim_store",
        lambda: SimpleNamespace(get=lambda ticket_id: claim),
    )

    result = server._canonicalize_governed_action_arguments(
        "service.ticket.update",
        {
            "ticket_id": 123,
            "return_work": True,
            "handoff_reason_class": "human_intervention_required",
            "blocker_fingerprint": "needs-onsite-access",
        },
    )
    assert result["payload"] == {
        "id": 123,
        "queueID": 29682833,
        "status": 1,
    }
    assert result["jason_policy_class"] == "ticket_work_handoff"


def test_handoff_rejects_caller_destination_override(monkeypatch):
    claim = SimpleNamespace(
        state="claimed",
        original_queue_id=29682833,
        original_status_id=1,
    )
    monkeypatch.setattr(
        server,
        "_ticket_work_claim_store",
        lambda: SimpleNamespace(get=lambda ticket_id: claim),
    )
    with pytest.raises(ValueError, match="UNSUPPORTED_ARGUMENTS"):
        server._canonicalize_governed_action_arguments(
            "service.ticket.update",
            {
                "ticket_id": 123,
                "return_work": True,
                "queueID": 999,
                "handoff_reason_class": "human_intervention_required",
                "blocker_fingerprint": "needs-onsite-access",
            },
        )


def test_start_fails_closed_when_device_has_no_exact_configuration(monkeypatch):
    calls = []

    def governed_read(*, capability_name, arguments):
        calls.append((capability_name, dict(arguments)))
        if capability_name == "service.ticket.read":
            return _ticket_read(_ticket(configuration_id=None))
        if capability_name == "endpoint.device.search":
            return {
                "status": "succeeded",
                "evidence": {
                    "resource_matches": [{
                        "resource_id": "device-uid-123",
                        "hostname": "DEVICE-123",
                    }]
                },
            }
        if capability_name == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "device-uid-123",
                        "hostname": "DEVICE-123",
                        "online": True,
                        "suspended": False,
                        "deleted": False,
                    }
                },
            }
        if capability_name == "service.configuration.search":
            return {
                "status": "succeeded",
                "evidence": {"data": {"items": []}},
            }
        raise AssertionError(capability_name)

    monkeypatch.setattr(server, "_governed_read", governed_read)
    monkeypatch.setattr(
        server,
        "_ticket_work_claim_store",
        lambda: SimpleNamespace(get=lambda ticket_id: None),
    )

    with pytest.raises(ValueError, match="CONFIGURATION_NOT_FOUND"):
        server._canonicalize_governed_action_arguments(
            "service.ticket.update",
            {
                "ticket_id": 123,
                "begin_work": True,
                "work_kind": "diagnostic",
                "device_name": "DEVICE-123",
            },
        )


def test_start_fails_closed_when_multiple_exact_configurations_exist(monkeypatch):
    def governed_read(*, capability_name, arguments):
        if capability_name == "service.ticket.read":
            return _ticket_read(_ticket(configuration_id=None))
        if capability_name == "endpoint.device.search":
            return {
                "status": "succeeded",
                "evidence": {
                    "resource_matches": [{
                        "resource_id": "device-uid-123",
                        "hostname": "DEVICE-123",
                    }]
                },
            }
        if capability_name == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "device-uid-123",
                        "hostname": "DEVICE-123",
                        "online": True,
                        "suspended": False,
                        "deleted": False,
                    }
                },
            }
        if capability_name == "service.configuration.search":
            item = {
                "isActive": True,
                "referenceTitle": "DEVICE-123",
                "referenceNumber": "device-uid-123",
                "companyID": 99,
            }
            return {
                "status": "succeeded",
                "evidence": {"data": {"items": [
                    {**item, "id": 1001},
                    {**item, "id": 1002},
                ]}},
            }
        raise AssertionError(capability_name)

    monkeypatch.setattr(server, "_governed_read", governed_read)
    monkeypatch.setattr(
        server,
        "_ticket_work_claim_store",
        lambda: SimpleNamespace(get=lambda ticket_id: None),
    )

    with pytest.raises(ValueError, match="CONFIGURATION_NOT_UNIQUE"):
        server._canonicalize_governed_action_arguments(
            "service.ticket.update",
            {
                "ticket_id": 123,
                "begin_work": True,
                "work_kind": "diagnostic",
                "device_name": "DEVICE-123",
            },
        )


@pytest.mark.parametrize("source_queue", [8, 29682833])
def test_start_moves_monitoring_or_helpdesk_ticket_to_jason_before_work(
    monkeypatch, source_queue
):
    ticket = _ticket(title="Generic ticket")
    ticket["queueID"] = source_queue

    monkeypatch.setattr(
        server,
        "_governed_read",
        lambda **kwargs: _ticket_read(ticket),
    )
    monkeypatch.setattr(
        server,
        "_ticket_work_claim_store",
        lambda: SimpleNamespace(get=lambda ticket_id: None),
    )

    result = server._canonicalize_governed_action_arguments(
        "service.ticket.update",
        {"ticket_id": 123, "begin_work": True, "work_kind": "diagnostic"},
    )

    assert result["payload"]["queueID"] == "Jason"
    assert result["payload"]["status"] == "In Progress"
    assert result["jason_original_queue_id"] == source_queue


def test_start_is_idempotent_for_ticket_already_claimed_by_jason(monkeypatch):
    ticket = _ticket(title="Generic ticket")
    ticket["queueID"] = 29683489
    ticket["status"] = 8
    claim = SimpleNamespace(
        state="claimed",
        original_queue_id=29682833,
        original_status_id=1,
        blocker_fingerprint="",
    )

    monkeypatch.setattr(
        server,
        "_governed_read",
        lambda **kwargs: _ticket_read(ticket),
    )
    monkeypatch.setattr(
        server,
        "_ticket_work_claim_store",
        lambda: SimpleNamespace(get=lambda ticket_id: claim),
    )

    result = server._canonicalize_governed_action_arguments(
        "service.ticket.update",
        {"ticket_id": 123, "begin_work": True, "work_kind": "diagnostic"},
    )

    assert result["payload"]["queueID"] == "Jason"
    assert result["payload"]["status"] == "In Progress"
    assert result["jason_original_queue_id"] == 29682833
    assert result["jason_original_status_id"] == 1


def test_internal_company_zero_allows_exact_configuration(monkeypatch):
    ticket = _ticket(configuration_id=None)
    ticket["companyID"] = 0

    def governed_read(*, capability_name, arguments):
        if capability_name == "endpoint.device.search":
            return {
                "status": "succeeded",
                "evidence": {
                    "resource_matches": [{
                        "resource_id": "device-uid-123",
                        "hostname": "DEVICE-123",
                    }]
                },
            }
        if capability_name == "service.configuration.search":
            assert arguments["company_id"] == 0
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "items": [{
                            "id": 1001,
                            "isActive": True,
                            "referenceTitle": "DEVICE-123",
                            "referenceNumber": "device-uid-123",
                            "companyID": 0,
                        }]
                    }
                },
            }
        raise AssertionError(capability_name)

    monkeypatch.setattr(server, "_governed_read", governed_read)
    assert server._exact_configuration_for_ticket_device(
        ticket=ticket,
        device_name="DEVICE-123",
    ) == 1001


def test_internal_company_zero_allows_existing_configuration(monkeypatch):
    ticket = _ticket(configuration_id=1001)
    ticket["companyID"] = 0

    def governed_read(*, capability_name, arguments):
        assert capability_name == "service.configuration.read"
        assert arguments == {"resource_id": 1001}
        return {
            "status": "succeeded",
            "evidence": {
                "data": {
                    "item": {
                        "id": 1001,
                        "isActive": True,
                        "referenceTitle": "DEVICE-123",
                        "referenceNumber": "device-uid-123",
                        "companyID": 0,
                    }
                }
            },
        }

    monkeypatch.setattr(server, "_governed_read", governed_read)
    result = server._validate_existing_ticket_configuration(
        ticket=ticket,
        configuration_id=1001,
    )
    assert result["id"] == 1001
    assert result["companyID"] == 0
