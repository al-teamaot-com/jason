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
