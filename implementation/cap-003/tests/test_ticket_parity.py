from __future__ import annotations

from jason_cap_003.context import AutotaskBusinessContext
from jason_cap_003.local_llm import OllamaBusinessContextAnalyzer


def test_cap003_projection_preserves_cap002_ticket_analysis_inputs() -> None:
    context = AutotaskBusinessContext(
        company={"id": 208, "companyName": "Example Company", "isActive": True},
        contacts=(),
        configurations=(),
        tickets=(
            {
                "id": 33,
                "ticketNumber": "T20260805.0064",
                "title": "Missing critical security patch",
                "description": "VulScan detected KB5104033 as missing.",
                "status": 1,
                "priority": 2,
                "dueDateTime": "2026-08-05T17:00:00Z",
                "providerInternalMetadata": "must-not-reach-model",
            },
        ),
        contracts=(),
        projects=(),
    )

    projected = OllamaBusinessContextAnalyzer._compact_context(context)

    assert projected["company"]["companyName"] == "Example Company"
    assert projected["record_counts"]["tickets"] == 1
    assert projected["tickets"] == [
        {
            "id": 33,
            "ticketNumber": "T20260805.0064",
            "title": "Missing critical security patch",
            "description": "VulScan detected KB5104033 as missing.",
            "status": 1,
            "priority": 2,
            "dueDateTime": "2026-08-05T17:00:00Z",
        }
    ]
    assert "providerInternalMetadata" not in projected["tickets"][0]


def test_cap003_ticket_context_is_bounded_without_losing_ticket_semantics() -> None:
    tickets = tuple(
        {
            "id": index,
            "ticketNumber": f"T{index:04d}",
            "title": f"Ticket {index}",
            "description": "x" * 2000,
        }
        for index in range(25)
    )
    context = AutotaskBusinessContext(
        company={"id": 208, "companyName": "Example Company"},
        contacts=(),
        configurations=(),
        tickets=tickets,
        contracts=(),
        projects=(),
    )

    projected = OllamaBusinessContextAnalyzer._compact_context(context)

    assert projected["record_counts"]["tickets"] == 25
    assert len(projected["tickets"]) == 10
    assert projected["tickets"][0]["ticketNumber"] == "T0000"
    assert projected["tickets"][0]["title"] == "Ticket 0"
    assert len(projected["tickets"][0]["description"]) <= 1203
