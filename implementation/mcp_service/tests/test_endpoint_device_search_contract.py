from jason_mcp import server


def _output(*, discovery_complete, incomplete_reason=None):
    data = {
        "resource_matches": [],
        "provider_data": {
            "discovery_mode": "hostname_local_enumeration",
            "hostname_reference": "MISSING",
            "pages": [
                {
                    "pageDetails": {
                        "totalCount": 749,
                    },
                    "devices": [],
                }
            ],
        },
        "discovery_complete": discovery_complete,
    }
    if incomplete_reason is not None:
        data["incomplete_reason"] = incomplete_reason

    return {
        "provider": "datto_rmm",
        "provider_capability": "datto_rmm.device.search",
        "data": data,
    }


def test_endpoint_search_projects_complete_zero_match_as_definitive_not_found():
    evidence = server._project_endpoint_search(
        _output(discovery_complete=True)
    )

    assert evidence["match_count"] == 0
    assert evidence["discovery_complete"] is True
    assert evidence["search"]["incomplete_reason"] is None


def test_endpoint_search_projects_incomplete_zero_match_as_indeterminate():
    evidence = server._project_endpoint_search(
        _output(
            discovery_complete=False,
            incomplete_reason="page_limit_reached",
        )
    )

    assert evidence["match_count"] == 0
    assert evidence["discovery_complete"] is False
    assert (
        evidence["search"]["incomplete_reason"]
        == "page_limit_reached"
    )


def test_endpoint_search_projects_bounded_identity_evidence():
    evidence = server._project_endpoint_search(
        {
            "provider": "datto_rmm",
            "provider_capability": "datto_rmm.device.search",
            "data": {
                "resource_matches": [{
                    "resource_id": "device-1",
                    "hostname": "PC-1",
                    "site": "Client A",
                    "site_id": "site-1",
                    "serial_number": "SERIAL-1",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                    "lan_ip": "192.168.1.10",
                    "wan_ip": "203.0.113.10",
                }],
                "provider_data": {
                    "discovery_mode": "hostname_local_enumeration",
                    "hostname_reference": "PC-1",
                    "pages": [],
                },
                "discovery_complete": True,
            },
        }
    )

    match = evidence["resource_matches"][0]
    assert match["serial_number"] == "SERIAL-1"
    assert match["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert match["lan_ip"] == "192.168.1.10"
    assert match["wan_ip"] == "203.0.113.10"
