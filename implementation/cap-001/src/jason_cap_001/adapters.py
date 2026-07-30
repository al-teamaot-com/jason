from __future__ import annotations

from typing import Any, Protocol


class TicketProvider(Protocol):
    def get_ticket(self, ticket_id: str, *, client_id: str) -> dict[str, Any]: ...


class AssetProvider(Protocol):
    def get_asset(self, asset_id: str, *, client_id: str) -> dict[str, Any]: ...


class EvidenceProvider(Protocol):
    def collect(self, request: dict[str, Any], *, client_id: str) -> list[dict[str, Any]]: ...


class ReasoningProvider(Protocol):
    def analyze(self, case_package: dict[str, Any]) -> dict[str, Any]: ...


class MemoryProvider(Protocol):
    def record_case(self, case_package: dict[str, Any]) -> None: ...

    def record_result(self, reasoning_result: dict[str, Any]) -> None: ...

    def record_outcome(self, outcome: dict[str, Any]) -> None: ...


class AuditProvider(Protocol):
    def append(self, event_type: str, payload: dict[str, Any]) -> None: ...


class TransitionProvider(Protocol):
    def record_transition(
        self,
        *,
        correlation_id: str,
        from_state: str,
        to_state: str,
        reason: str,
        case_id: str | None = None,
    ) -> None: ...


class ContextValidator(Protocol):
    def validate(self, request: dict[str, Any]) -> Any: ...
