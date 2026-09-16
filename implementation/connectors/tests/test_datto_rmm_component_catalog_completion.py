from __future__ import annotations

from connectors.datto_rmm.automation_reads import DattoRmmAutomationReadConnector


def test_component_search_pages_until_declared_total_before_name_filtering(monkeypatch):
    connector = object.__new__(DattoRmmAutomationReadConnector)

    first_page = {
        "components": [
            {"uid": f"uid-{i}", "name": f"Component {i}"}
            for i in range(250)
        ],
        "pageDetails": {
            "count": 250,
            "totalCount": 251,
            "nextPageUrl": None,
        },
    }

    second_page = {
        "components": [
            {
                "uid": "target-uid",
                "name": "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024",
            }
        ],
        "pageDetails": {
            "count": 1,
            "totalCount": 251,
            "nextPageUrl": None,
        },
    }

    monkeypatch.setattr(
        connector,
        "_prepare_provider_request",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        connector,
        "_execute_prepared_request",
        lambda **kwargs: second_page,
    )
    monkeypatch.setattr(
        connector,
        "_normalize_result",
        lambda capability, payload: payload,
    )

    class RequestLike:
        arguments = {
            "name": "Datto EDR Force Reinstall",
            "page": 0,
            "max": 250,
        }

    completed = connector._complete_component_collection(
        request=RequestLike(),
        initial_data=first_page,
        credentials={},
        access_token="token",
        token_type="Bearer",
    )
    result = connector._canonical_component_search_result(
        payload=completed,
        arguments=RequestLike.arguments,
    )

    assert result["discovery_complete"] is True
    assert result["match_count"] == 1
    assert result["resource_matches"][0]["resource_id"] == "target-uid"


def test_component_search_fails_closed_when_full_page_has_no_pagination_metadata():
    connector = object.__new__(DattoRmmAutomationReadConnector)

    first_page = {
        "components": [
            {"uid": f"uid-{i}", "name": f"Component {i}"}
            for i in range(250)
        ]
    }

    class RequestLike:
        arguments = {"page": 0, "max": 250}

    try:
        connector._complete_component_collection(
            request=RequestLike(),
            initial_data=first_page,
            credentials={},
            access_token="token",
            token_type="Bearer",
        )
    except ValueError as exc:
        assert "pagination metadata missing" in str(exc)
    else:
        raise AssertionError("incomplete full-page discovery must fail closed")
