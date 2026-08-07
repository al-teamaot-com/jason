from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from jason_cap_003.context import AutotaskBusinessContext

from .models import OperationalSignal


class AutotaskOperationalSignalProducer:
    """Normalize bounded CAP-003 Autotask context into operational signals."""

    source_provider = "autotask"

    def __init__(self, *, stale_ticket_days: int = 14) -> None:
        if stale_ticket_days < 1 or stale_ticket_days > 365:
            raise ValueError("stale_ticket_days must be between 1 and 365")
        self._stale_ticket_days = stale_ticket_days

    def produce(
        self,
        *,
        organization_id: str,
        context: AutotaskBusinessContext,
        as_of: datetime,
    ) -> tuple[OperationalSignal, ...]:
        organization_id = organization_id.strip()
        if not organization_id:
            raise ValueError("organization_id must be non-empty")
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        as_of = as_of.astimezone(timezone.utc)

        company_id = context.company_id
        company_name = str(context.company.get("companyName", "")).strip()
        if not company_name:
            raise ValueError("Autotask context companyName must be non-empty")

        signals: list[OperationalSignal] = []
        for ticket in context.tickets:
            signals.extend(
                self._ticket_signals(
                    organization_id=organization_id,
                    company_id=company_id,
                    company_name=company_name,
                    ticket=ticket,
                    as_of=as_of,
                )
            )
        for configuration in context.configurations:
            signal = self._configuration_signal(
                organization_id=organization_id,
                company_id=company_id,
                company_name=company_name,
                configuration=configuration,
                as_of=as_of,
            )
            if signal is not None:
                signals.append(signal)

        signals.sort(
            key=lambda signal: (
                signal.category,
                signal.evidence_reference or "",
                signal.summary,
            )
        )
        return tuple(signals)

    def _ticket_signals(
        self,
        *,
        organization_id: str,
        company_id: str,
        company_name: str,
        ticket: Mapping[str, Any],
        as_of: datetime,
    ) -> tuple[OperationalSignal, ...]:
        if self._has_value(ticket.get("completedDate")):
            return ()

        ticket_id = self._identifier(ticket)
        ticket_number = str(ticket.get("ticketNumber", ticket_id)).strip() or ticket_id
        title = str(ticket.get("title", "Untitled ticket")).strip() or "Untitled ticket"
        evidence = f"autotask:ticket:{ticket_id}"
        results: list[OperationalSignal] = []

        due = self._parse_datetime(ticket.get("dueDateTime"))
        if due is not None and due < as_of:
            results.append(
                OperationalSignal(
                    source_provider=self.source_provider,
                    organization_id=organization_id,
                    subject_type="client",
                    subject_id=company_id,
                    subject_name=company_name,
                    category="ticket-overdue",
                    severity="high",
                    summary=f"Overdue ticket {ticket_number}: {title}",
                    recommended_action="Review ownership, current status, and next action for the overdue ticket.",
                    evidence_reference=evidence,
                )
            )

        last_activity = self._parse_datetime(ticket.get("lastActivityDate"))
        if last_activity is not None:
            age_days = (as_of - last_activity.astimezone(timezone.utc)).days
            if age_days >= self._stale_ticket_days:
                results.append(
                    OperationalSignal(
                        source_provider=self.source_provider,
                        organization_id=organization_id,
                        subject_type="client",
                        subject_id=company_id,
                        subject_name=company_name,
                        category="ticket-stale",
                        severity="medium",
                        summary=(
                            f"Ticket {ticket_number} has had no recorded activity for "
                            f"{age_days} days: {title}"
                        ),
                        recommended_action="Confirm whether the ticket still requires work, customer response, or closure.",
                        evidence_reference=evidence,
                    )
                )

        return tuple(results)

    def _configuration_signal(
        self,
        *,
        organization_id: str,
        company_id: str,
        company_name: str,
        configuration: Mapping[str, Any],
        as_of: datetime,
    ) -> OperationalSignal | None:
        active = configuration.get("active")
        if active is False or str(active).strip().lower() == "false":
            return None

        expiration = self._parse_datetime(configuration.get("warrantyExpirationDate"))
        if expiration is None or expiration >= as_of:
            return None

        configuration_id = self._identifier(configuration)
        name = str(
            configuration.get("referenceTitle", configuration_id)
        ).strip() or configuration_id
        return OperationalSignal(
            source_provider=self.source_provider,
            organization_id=organization_id,
            subject_type="client",
            subject_id=company_id,
            subject_name=company_name,
            category="configuration-warranty-expired",
            severity="medium",
            summary=f"Active configuration {name} has an expired warranty.",
            recommended_action="Review replacement lifecycle, warranty coverage, or accepted-risk documentation.",
            evidence_reference=f"autotask:configuration:{configuration_id}",
        )

    @staticmethod
    def _identifier(record: Mapping[str, Any]) -> str:
        value = record.get("id")
        if value is None or not str(value).strip():
            raise ValueError("Autotask record is missing a durable provider identifier")
        return str(value).strip()

    @staticmethod
    def _has_value(value: object) -> bool:
        return value is not None and bool(str(value).strip())

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
