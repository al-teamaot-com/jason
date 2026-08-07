from datetime import datetime, timezone

from jason_cap_003.context import AutotaskBusinessContext
from jason_cap_004.autotask_signals import AutotaskOperationalSignalProducer
from jason_cap_004.service import OperationalBriefingService


AS_OF = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def context(*, tickets=(), configurations=()):
    return AutotaskBusinessContext(
        company={"id": 208, "companyName": "Example Client"},
        contacts=(),
        configurations=tuple(configurations),
        tickets=tuple(tickets),
        contracts=(),
        projects=(),
    )


def test_overdue_and_stale_ticket_produce_deterministic_client_signals() -> None:
    producer = AutotaskOperationalSignalProducer(stale_ticket_days=14)

    signals = producer.produce(
        organization_id="aot",
        context=context(
            tickets=(
                {
                    "id": 33,
                    "ticketNumber": "T1",
                    "title": "Backup failure",
                    "dueDateTime": "2026-08-01T12:00:00Z",
                    "lastActivityDate": "2026-07-01T12:00:00Z",
                    "completedDate": None,
                },
            )
        ),
        as_of=AS_OF,
    )

    assert [signal.category for signal in signals] == ["ticket-overdue", "ticket-stale"]
    assert all(signal.subject_type == "client" for signal in signals)
    assert all(signal.subject_id == "208" for signal in signals)
    assert signals[0].severity == "high"
    assert signals[0].evidence_reference == "autotask:ticket:33"


def test_completed_ticket_does_not_create_attention_signal() -> None:
    signals = AutotaskOperationalSignalProducer().produce(
        organization_id="aot",
        context=context(
            tickets=(
                {
                    "id": 33,
                    "ticketNumber": "T1",
                    "title": "Resolved issue",
                    "dueDateTime": "2026-07-01T12:00:00Z",
                    "lastActivityDate": "2026-07-01T12:00:00Z",
                    "completedDate": "2026-07-02T12:00:00Z",
                },
            )
        ),
        as_of=AS_OF,
    )

    assert signals == ()


def test_expired_active_configuration_warranty_creates_medium_signal() -> None:
    signals = AutotaskOperationalSignalProducer().produce(
        organization_id="aot",
        context=context(
            configurations=(
                {
                    "id": 22,
                    "referenceTitle": "SERVER-01",
                    "active": True,
                    "warrantyExpirationDate": "2026-01-01T00:00:00Z",
                },
            )
        ),
        as_of=AS_OF,
    )

    assert len(signals) == 1
    assert signals[0].category == "configuration-warranty-expired"
    assert signals[0].severity == "medium"
    assert signals[0].evidence_reference == "autotask:configuration:22"


def test_inactive_configuration_is_not_signaled() -> None:
    signals = AutotaskOperationalSignalProducer().produce(
        organization_id="aot",
        context=context(
            configurations=(
                {
                    "id": 22,
                    "referenceTitle": "OLD-PC",
                    "active": False,
                    "warrantyExpirationDate": "2020-01-01T00:00:00Z",
                },
            )
        ),
        as_of=AS_OF,
    )

    assert signals == ()


def test_autotask_signals_feed_provider_neutral_briefing_without_provider_logic() -> None:
    signals = AutotaskOperationalSignalProducer().produce(
        organization_id="aot",
        context=context(
            tickets=(
                {
                    "id": 33,
                    "ticketNumber": "T1",
                    "title": "Overdue issue",
                    "dueDateTime": "2026-08-01T12:00:00Z",
                    "lastActivityDate": "2026-08-06T12:00:00Z",
                    "completedDate": None,
                },
            ),
            configurations=(
                {
                    "id": 22,
                    "referenceTitle": "SERVER-01",
                    "active": True,
                    "warrantyExpirationDate": "2026-01-01T00:00:00Z",
                },
            ),
        ),
        as_of=AS_OF,
    )

    briefing = OperationalBriefingService().build(
        organization_id="aot",
        signals=signals,
    )

    assert len(briefing.attention_items) == 1
    item = briefing.attention_items[0]
    assert item.subject_name == "Example Client"
    assert item.providers == ("autotask",)
    assert item.highest_severity == "high"
    assert set(item.categories) == {
        "configuration-warranty-expired",
        "ticket-overdue",
    }
