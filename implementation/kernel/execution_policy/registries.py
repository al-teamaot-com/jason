from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from kernel.execution_policy.contracts import (
    ExecutionMode,
    PriceConfidence,
)


@dataclass(frozen=True, slots=True)
class PricingEntry:
    provider_id: str
    model_id: str
    execution_mode: ExecutionMode
    input_cost_per_million_tokens: Decimal
    output_cost_per_million_tokens: Decimal
    cached_input_cost_per_million_tokens: Decimal = Decimal("0")
    request_cost: Decimal = Decimal("0")
    infrastructure_cost_per_execution: Decimal = Decimal("0")
    internal_compute_cost_per_second: Decimal = Decimal("0")
    currency: str = "USD"
    pricing_version: str = "unknown"
    confidence: PriceConfidence = PriceConfidence.UNKNOWN
    active: bool = True

    def __post_init__(self) -> None:
        values = (
            self.input_cost_per_million_tokens,
            self.output_cost_per_million_tokens,
            self.cached_input_cost_per_million_tokens,
            self.request_cost,
            self.infrastructure_cost_per_execution,
            self.internal_compute_cost_per_second,
        )
        if any(value < 0 for value in values):
            raise ValueError("Pricing values must be non-negative.")


class InMemoryPricingRegistry:
    def __init__(self, entries: Iterable[PricingEntry] = ()) -> None:
        self._entries: dict[tuple[str, str, ExecutionMode], PricingEntry] = {}
        for entry in entries:
            self.add(entry)

    def add(self, entry: PricingEntry) -> None:
        key = (entry.provider_id, entry.model_id, entry.execution_mode)
        if key in self._entries:
            raise ValueError("Duplicate pricing entry.")
        self._entries[key] = entry

    def get(
        self,
        *,
        provider_id: str,
        model_id: str,
        execution_mode: ExecutionMode,
    ) -> PricingEntry | None:
        entry = self._entries.get((provider_id, model_id, execution_mode))
        if entry is None or not entry.active:
            return None
        return entry
