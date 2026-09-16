from __future__ import annotations

import pytest

from connectors.datto_rmm.automation_reads import (
    DattoRmmAutomationReadConnector,
)


TARGET = (
    "Datto EDR Force Reinstall and Upgrade "
    "[WIN] AOT 09162024"
)


class RequestLike:
    arguments = {
        "name": "Datto EDR Force Reinstall",
        "page": 0,
        "max": 100,
    }


def connector_for(responses):
    connector = object.__new__(
        DattoRmmAutomationReadConnector
    )

    calls = []
    iterator = iter(responses)

    def prepare(**kwargs):
        calls.append(
            dict(kwargs["arguments"])
        )
        return object()

    connector._prepare_provider_request = prepare
    connector._execute_prepared_request = (
        lambda **kwargs: next(iterator)
    )
    connector._normalize_result = (
        lambda capability, payload: payload
    )
    connector._record_component_completion = (
        lambda **kwargs: None
    )

    return connector, calls


def test_component_search_ignores_misleading_total_count():
    first_page = {
        "components": [
            {
                "uid": f"uid-{i}",
                "name": f"Component {i}",
            }
            for i in range(100)
        ],
        "pageDetails": {
            "count": 100,
            "totalCount": 100,
            "nextPageUrl": None,
        },
    }

    second_page = {
        "components": [
            {
                "uid": "target-uid",
                "name": TARGET,
            }
        ],
        "pageDetails": {
            "count": 1,
            "totalCount": 1,
            "nextPageUrl": None,
        },
    }

    terminal_page = {
        "components": [],
        "pageDetails": {
            "count": 0,
            "totalCount": 0,
            "nextPageUrl": None,
        },
    }

    connector, calls = connector_for(
        [
            second_page,
            terminal_page,
        ]
    )

    completed = (
        connector._complete_component_collection(
            request=RequestLike(),
            initial_data=first_page,
            credentials={},
            access_token="token",
            token_type="Bearer",
        )
    )

    result = (
        connector._canonical_component_search_result(
            payload=completed,
            arguments=RequestLike.arguments,
        )
    )

    assert calls == [
        {
            "page": 1,
            "max": 100,
        },
        {
            "page": 2,
            "max": 100,
        },
    ]

    assert len(
        completed["components"]
    ) == 101

    assert (
        completed["pageDetails"]["totalCount"]
        == 101
    )

    assert result["discovery_complete"] is True
    assert result["match_count"] == 1

    assert (
        result["resource_matches"][0]["resource_id"]
        == "target-uid"
    )


def test_component_search_fails_closed_on_repeated_page():
    first_page = {
        "components": [
            {
                "uid": f"uid-{i}",
                "name": f"Component {i}",
            }
            for i in range(100)
        ],
        "pageDetails": {
            "count": 100,
            "totalCount": 100,
            "nextPageUrl": None,
        },
    }

    connector, calls = connector_for(
        [
            first_page,
        ]
    )

    with pytest.raises(
        ValueError,
        match="repeated previously returned records",
    ):
        connector._complete_component_collection(
            request=RequestLike(),
            initial_data=first_page,
            credentials={},
            access_token="token",
            token_type="Bearer",
        )

    assert calls == [
        {
            "page": 1,
            "max": 100,
        }
    ]


def test_component_search_probes_after_short_page_until_empty():
    first_page = {
        "components": [
            {
                "uid": "first",
                "name": "First Component",
            }
        ],
        "pageDetails": {
            "count": 1,
            "totalCount": 1,
            "nextPageUrl": None,
        },
    }

    terminal_page = {
        "components": [],
        "pageDetails": {
            "count": 0,
            "totalCount": 0,
            "nextPageUrl": None,
        },
    }

    connector, calls = connector_for(
        [
            terminal_page,
        ]
    )

    completed = (
        connector._complete_component_collection(
            request=RequestLike(),
            initial_data=first_page,
            credentials={},
            access_token="token",
            token_type="Bearer",
        )
    )

    assert calls == [
        {
            "page": 1,
            "max": 100,
        }
    ]

    assert len(
        completed["components"]
    ) == 1
