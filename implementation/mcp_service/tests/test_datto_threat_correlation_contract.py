from jason_mcp import server


DEVICE_UID = "69571572-83f7-1e33-9cdf-01717d4e74a4"
AGENT_ID = "0cf9b495-879b-4b6c-8c60-ac229e01d136"
DRMM_ALERT_UID = "bd0882e0-8700-4985-ad89-f789b865c76e"
EDR_ALERT_ID = "c3aa92e3-92af-4c8f-889a-51bafa50790f"


def result(capability, data=None, *, items=None):
    evidence = {"data": data or {}}
    if items is not None:
        evidence = {"items": items}
    return {
        "status": "succeeded",
        "capability": capability,
        "correlation_id": "corr-child",
        "evidence": evidence,
    }


def drmm_alert():
    return {
        "alertUid": DRMM_ALERT_UID,
        "timestamp": 1789720844000,
        "alertContext": {
            "@class": "endpoint_security_threat_ctx",
            "esAlertId": "15884344",
            "description": "Detected threat from Datto AV",
        },
        "alertSourceInfo": {"deviceUid": DEVICE_UID},
    }


def edr_detection(alert_id=EDR_ALERT_ID):
    return {
        "alert_id": alert_id,
        "agent_id": AGENT_ID,
        "device_id": DEVICE_UID,
        "source_type": "av",
        "signal": True,
        "event_time": "2026-09-18T08:40:41.000Z",
    }


def fake_governed_read(*, capability_name, arguments):
    if capability_name == "endpoint.security.status.read":
        return result(
            capability_name,
            {
                "resource_matches": [
                    {
                        "resource_id": DEVICE_UID,
                        "agent_id": AGENT_ID,
                        "hostname": "aot-50282",
                    }
                ]
            },
        )
    if capability_name == "endpoint.alert.search":
        return result(capability_name, items=[])
    if capability_name == "endpoint.alert.history.search":
        return result(capability_name, {"alerts": [drmm_alert()]})
    if capability_name == "endpoint.security.detection.search":
        assert arguments["agent_id"] == AGENT_ID
        return result(capability_name, {"alerts": [edr_detection()]})
    if capability_name == "endpoint.security.detection.read":
        assert arguments == {"alert_id": EDR_ALERT_ID}
        return result(
            capability_name,
            {
                "alert_id": EDR_ALERT_ID,
                "threat_status": "Quarantined",
                "quarantined": True,
            },
        )
    raise AssertionError(capability_name)


def test_numeric_drmm_threat_reference_resolves_to_exact_edr_alert(monkeypatch):
    monkeypatch.setattr(server, "_governed_read", fake_governed_read)

    result_value = server._governed_datto_threat_correlation_read(
        {
            "alert_id": "15884344",
            "resource_id": DEVICE_UID,
            "drmm_alert_uid": DRMM_ALERT_UID,
        }
    )

    assert result_value["status"] == "succeeded"
    assert result_value["evidence"]["data"]["alert_id"] == EDR_ALERT_ID
    assert result_value["correlation"] == {
        "threat_reference": "15884344",
        "drmm_alert_uid": DRMM_ALERT_UID,
        "edr_alert_id": EDR_ALERT_ID,
        "device_uid": DEVICE_UID,
        "agent_id": AGENT_ID,
        "event_delta_seconds": 3.0,
        "basis": (
            "exact_device_uid+exact_agent_id+"
            "drmm_threat_reference+event_time_window"
        ),
        "fail_closed": True,
    }


def test_correlation_fails_closed_when_two_edr_alerts_match(monkeypatch):
    def ambiguous_read(*, capability_name, arguments):
        if capability_name == "endpoint.security.detection.search":
            return result(
                capability_name,
                {
                    "alerts": [
                        edr_detection("11111111-1111-1111-1111-111111111111"),
                        edr_detection("22222222-2222-2222-2222-222222222222"),
                    ]
                },
            )
        return fake_governed_read(
            capability_name=capability_name,
            arguments=arguments,
        )

    monkeypatch.setattr(server, "_governed_read", ambiguous_read)

    result_value = server._governed_datto_threat_correlation_read(
        {
            "threat_reference": "15884344",
            "resource_id": DEVICE_UID,
        }
    )

    assert result_value["status"] == "failed"
    assert (
        result_value["error_code"]
        == "DATTO_THREAT_CORRELATION_EDR_ALERT_AMBIGUOUS"
    )


def test_uuid_alert_id_keeps_existing_direct_read_path(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        server,
        "_dynamic_read_capability_allowed",
        lambda capability_name: capability_name == "endpoint.security.detection.read",
    )

    def direct_read(*, capability_name, arguments):
        captured["capability"] = capability_name
        captured["arguments"] = dict(arguments)
        return result(capability_name, {"alert_id": EDR_ALERT_ID})

    monkeypatch.setattr(server, "_governed_read", direct_read)

    result_value = server.execute_read_capability(
        capability="endpoint.security.detection.read",
        arguments={"alert_id": EDR_ALERT_ID},
    )

    assert result_value["status"] == "succeeded"
    assert captured == {
        "capability": "endpoint.security.detection.read",
        "arguments": {"alert_id": EDR_ALERT_ID},
    }


def test_alert_resolution_action_canonicalizes_exact_target():
    args = server._canonicalize_governed_action_arguments(
        "endpoint.alert.resolve",
        {
            "alert_uid": DRMM_ALERT_UID,
            "resource_id": DEVICE_UID,
        },
    )

    assert args == {
        "alert_uid": DRMM_ALERT_UID,
        "device_uid": DEVICE_UID,
    }


def test_alert_resolution_action_rejects_extra_arguments():
    try:
        server._canonicalize_governed_action_arguments(
            "endpoint.alert.resolve",
            {
                "alert_uid": DRMM_ALERT_UID,
                "device_uid": DEVICE_UID,
                "reason": "caller-controlled provider text",
            },
        )
    except ValueError as exc:
        assert "DATTO_ALERT_RESOLVE_UNSUPPORTED_ARGUMENTS" in str(exc)
    else:
        raise AssertionError("unsupported action arguments must fail closed")


def test_alert_resolution_projection_exposes_only_verified_fields():
    projected = server._project_action_result(
        "endpoint.alert.resolve",
        {
            "data": {
                "status": "verified",
                "alert_uid": DRMM_ALERT_UID,
                "device_uid": DEVICE_UID,
                "resolved": True,
                "already_resolved": False,
                "mutation_performed": True,
                "readback_verified": True,
                "provider_secret": "must-not-escape",
            }
        },
    )

    assert projected == {
        "raw_provider_evidence_exposed": False,
        "status": "verified",
        "alert_uid": DRMM_ALERT_UID,
        "device_uid": DEVICE_UID,
        "resolved": True,
        "already_resolved": False,
        "mutation_performed": True,
        "readback_verified": True,
    }


def test_edr_scan_action_canonicalizes_exact_target():
    args = server._canonicalize_governed_action_arguments(
        "endpoint.security.scan.start",
        {
            "device_uid": DEVICE_UID,
            "agent_id": AGENT_ID,
            "scan_type": "Quick",
        },
    )
    assert args == {
        "resource_id": DEVICE_UID,
        "agent_id": AGENT_ID,
        "scan_type": "quick",
    }


def test_edr_scan_action_rejects_unknown_fields():
    try:
        server._canonicalize_governed_action_arguments(
            "endpoint.security.scan.start",
            {
                "resource_id": DEVICE_UID,
                "agent_id": AGENT_ID,
                "scan_type": "quick",
                "options": {"unsafe": True},
            },
        )
    except ValueError as exc:
        assert "DATTO_EDR_SCAN_UNSUPPORTED_ARGUMENTS" in str(exc)
    else:
        raise AssertionError("scan action must reject caller-supplied provider options")


def test_edr_scan_projection_hides_provider_payload():
    projected = server._project_action_result(
        "endpoint.security.scan.start",
        {
            "data": {
                "status": "accepted",
                "resource_id": DEVICE_UID,
                "agent_id": AGENT_ID,
                "scan_type": "quick",
                "task_name": "Scan - AV Quick",
                "task_id": "task-123",
                "provider_accepted": True,
                "readback_required": True,
                "provider_raw": {"secret": "must-not-escape"},
            }
        },
    )
    assert projected == {
        "raw_provider_evidence_exposed": False,
        "status": "accepted",
        "resource_id": DEVICE_UID,
        "agent_id": AGENT_ID,
        "scan_type": "quick",
        "task_name": "Scan - AV Quick",
        "task_id": "task-123",
        "provider_accepted": True,
        "readback_required": True,
    }
