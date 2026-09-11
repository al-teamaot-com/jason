from __future__ import annotations

import pytest

from orchestrator.real_record_correlation_sample import (
    CorrelationSampleSelectionError,
    select_autotask_ticket_sample,
)


def test_prefers_configuration_link_without_using_provider_order_as_identity() -> None:
    selection = select_autotask_ticket_sample(
        [
            {"id": 901, "ticketNumber": "T1"},
            {"id": 902, "ticketNumber": "T2", "configurationItemID": 44},
            {"id": 903, "ticketNumber": "T3"},
        ],
        maximum_records=25,
    )

    assert selection.ticket_number == "T2"
    assert selection.ticket_id == "902"
    assert selection.candidate_count == 3
    assert selection.configuration_linked_candidate_count == 1
    assert selection.selection_basis == "greatest_provider_id_with_configuration_link"


def test_selects_greatest_durable_id_within_equally_suitable_sample() -> None:
    selection = select_autotask_ticket_sample(
        [
            {"id": 11, "ticketNumber": "T11", "configurationItemID": 8},
            {"id": 19, "ticketNumber": "T19", "configurationItemID": 9},
            {"id": 15, "ticketNumber": "T15", "configurationItemID": 10},
        ],
        maximum_records=25,
    )

    assert selection.ticket_number == "T19"
    assert selection.ticket_id == "19"


def test_sanitized_metadata_hashes_identifiers_instead_of_persisting_them() -> None:
    selection = select_autotask_ticket_sample(
        [{"id": 123, "ticketNumber": "T20260910.001", "configurationItemID": 5}],
        maximum_records=25,
    )

    metadata = selection.sanitized_metadata()

    assert "ticket_number" not in metadata
    assert "ticket_id" not in metadata
    assert "selected_ticket_selector_sha256" in metadata
    assert "selected_ticket_resource_sha256" in metadata
    assert metadata["selected_ticket_selector_sha256"] != "T20260910.001"
    assert metadata["selected_ticket_resource_sha256"] != "123"
    assert len(str(metadata["selected_ticket_selector_sha256"])) == 64
    assert len(str(metadata["selected_ticket_resource_sha256"])) == 64


def test_rejects_empty_malformed_or_over_bound_samples() -> None:
    with pytest.raises(CorrelationSampleSelectionError, match="no tickets"):
        select_autotask_ticket_sample([], maximum_records=25)

    with pytest.raises(CorrelationSampleSelectionError, match="bounded record limit"):
        select_autotask_ticket_sample(
            [{"id": index, "ticketNumber": f"T{index}"} for index in range(3)],
            maximum_records=2,
        )

    with pytest.raises(CorrelationSampleSelectionError, match="malformed"):
        select_autotask_ticket_sample(  # type: ignore[arg-type]
            [{"id": 1, "ticketNumber": "T1"}, "bad"],
            maximum_records=25,
        )


def test_does_not_treat_missing_ticket_identity_as_a_candidate() -> None:
    selection = select_autotask_ticket_sample(
        [
            {"id": 1},
            {"ticketNumber": "T2"},
            {"id": 3, "ticketNumber": "T3"},
        ],
        maximum_records=25,
    )

    assert selection.ticket_number == "T3"
    assert selection.candidate_count == 1
