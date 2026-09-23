import pytest

from connectors.core.provider_adaptation import (
    BoundedCollectionReadAdapter,
    ProviderEvidenceInconsistentError,
)


def test_consistent_nonempty_collection_requires_no_probe():
    calls = []

    adapter = BoundedCollectionReadAdapter()

    result = adapter.recover(
        payload={
            "pageDetails": {"count": 2, "totalCount": 2},
            "sites": [{"name": "A"}, {"name": "B"}],
        },
        collection_key="sites",
        request_arguments={},
        probe=lambda args: calls.append(args),
    )

    assert len(result.payload["sites"]) == 2
    assert result.observation is None
    assert calls == []


def test_empty_collection_with_declared_records_recovers_from_bounded_probe():
    calls = []

    def probe(arguments):
        calls.append(dict(arguments))
        if arguments["page"] == 0 and arguments["max"] == 25:
            return {
                "pageDetails": {
                    "count": 25,
                    "totalCount": 46,
                },
                "sites": [{"name": f"Site {n}"} for n in range(25)],
            }
        return {
            "pageDetails": {
                "count": 0,
                "totalCount": 46,
            },
            "sites": [],
        }

    adapter = BoundedCollectionReadAdapter(max_probes=5)

    result = adapter.recover(
        payload={
            "pageDetails": {
                "count": 0,
                "totalCount": 46,
                "prevPageUrl": (
                    "https://provider.example/sites?max=250&page=0"
                ),
            },
            "sites": [],
        },
        collection_key="sites",
        request_arguments={"page": 1, "max": 250},
        probe=probe,
    )

    assert len(result.payload["sites"]) == 25
    assert result.observation is not None
    assert result.observation.recovered is True
    assert result.observation.accepted_arguments == {
        "page": 0,
        "max": 25,
    }
    assert calls


def test_inconsistent_collection_fails_closed_after_probe_budget():
    adapter = BoundedCollectionReadAdapter(max_probes=3)

    with pytest.raises(
        ProviderEvidenceInconsistentError,
        match="reported 46 sites",
    ):
        adapter.recover(
            payload={
                "pageDetails": {
                    "count": 0,
                    "totalCount": 46,
                    "prevPageUrl": (
                        "https://provider.example/sites?max=250&page=0"
                    ),
                },
                "sites": [],
            },
            collection_key="sites",
            request_arguments={"page": 1, "max": 250},
            probe=lambda arguments: {
                "pageDetails": {
                    "count": 0,
                    "totalCount": 46,
                },
                "sites": [],
            },
        )


def test_zero_total_empty_collection_is_valid_empty_evidence():
    calls = []

    adapter = BoundedCollectionReadAdapter()

    result = adapter.recover(
        payload={
            "pageDetails": {
                "count": 0,
                "totalCount": 0,
            },
            "sites": [],
        },
        collection_key="sites",
        request_arguments={},
        probe=lambda args: calls.append(args),
    )

    assert result.payload["sites"] == []
    assert result.observation is None
    assert calls == []


def test_complete_collection_aggregates_provider_pages():
    calls = []

    first = {
        "pageDetails": {
            "count": 25,
            "totalCount": 46,
            "nextPageUrl": "https://provider.example/sites?max=25&page=1",
        },
        "sites": [{"name": f"Site {n}"} for n in range(1, 26)],
    }

    def probe(arguments):
        calls.append(dict(arguments))
        assert arguments == {"page": 1, "max": 25}
        return {
            "pageDetails": {
                "count": 21,
                "totalCount": 46,
                "nextPageUrl": None,
            },
            "sites": [
                {"name": f"Site {n}"}
                for n in range(26, 47)
            ],
        }

    adapter = BoundedCollectionReadAdapter()

    result = adapter.recover(
        payload=first,
        collection_key="sites",
        request_arguments={
            "result_intent": "enumerate",
            "completeness_requirement": "complete",
        },
        probe=probe,
        complete=True,
    )

    assert len(result.payload["sites"]) == 46
    assert result.payload["pageDetails"]["count"] == 46
    assert result.observation is not None
    assert result.observation.complete is True
    assert result.observation.pages_aggregated == 2
    assert result.observation.final_count == 46
    assert calls == [{"page": 1, "max": 25}]
