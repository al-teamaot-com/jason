"""Configuration-driven account registry.

Accounts are data, not code. Adding or retiring an account should not require a
new reconciliation implementation.
"""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import AccountStatus, FinanceAccountConfig


class FinanceAccountRegistry:
    def __init__(self, records: dict[str, FinanceAccountConfig]) -> None:
        self._records = dict(records)

    @classmethod
    def from_records(cls, records: Iterable[FinanceAccountConfig]) -> "FinanceAccountRegistry":
        by_id: dict[str, FinanceAccountConfig] = {}
        enabled_identity: set[tuple[str, str]] = set()
        for record in records:
            if record.account_id in by_id:
                raise ValueError(f"duplicate finance account_id: {record.account_id}")
            by_id[record.account_id] = record
            if record.status in {AccountStatus.PILOT, AccountStatus.ACTIVE}:
                identity = (record.institution.casefold(), record.masked_identifier.casefold())
                if identity in enabled_identity:
                    raise ValueError(
                        "multiple enabled finance accounts share institution/masked identifier"
                    )
                enabled_identity.add(identity)
        return cls(by_id)

    def resolve(self, account_id: str) -> FinanceAccountConfig | None:
        if not account_id.strip():
            raise ValueError("account_id is required")
        record = self._records.get(account_id)
        if record is None:
            return None
        if record.status not in {AccountStatus.PILOT, AccountStatus.ACTIVE}:
            return None
        return record

    def get_any_status(self, account_id: str) -> FinanceAccountConfig | None:
        if not account_id.strip():
            raise ValueError("account_id is required")
        return self._records.get(account_id)

    def enabled_accounts(self) -> tuple[FinanceAccountConfig, ...]:
        return tuple(
            sorted(
                (
                    record
                    for record in self._records.values()
                    if record.status in {AccountStatus.PILOT, AccountStatus.ACTIVE}
                ),
                key=lambda record: record.account_id,
            )
        )
