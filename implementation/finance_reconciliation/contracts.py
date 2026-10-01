"""Canonical, provider-neutral contracts for finance reconciliation.

This module deliberately contains no provider credentials, runtime registration,
Teams sending, bank connectivity, Excel writes, or production mutation hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
import re


class AccountType(str, Enum):
    BANK_CHECKING = "bank_checking"
    BANK_SAVINGS = "bank_savings"
    CREDIT_CARD = "credit_card"


class AccountStatus(str, Enum):
    PILOT = "pilot"
    ACTIVE = "active"
    INACTIVE = "inactive"
    RETIRED = "retired"


class DocumentKind(str, Enum):
    NATIVE_TEXT = "native_text"
    HYBRID = "hybrid"
    SCANNED = "scanned"


class BalanceEffect(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"


class MatchState(str, Enum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True, slots=True)
class SourceLocation:
    document_sha256: str
    page_number: int
    bbox: tuple[float, float, float, float] | None = None
    text_excerpt: str | None = None

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.document_sha256):
            raise ValueError("document_sha256 must be a 64-character SHA-256 hex digest")
        if self.page_number < 1:
            raise ValueError("page_number must be >= 1")
        if self.bbox is not None:
            x0, y0, x1, y1 = self.bbox
            if x1 <= x0 or y1 <= y0:
                raise ValueError("bbox must have positive width and height")


@dataclass(frozen=True, slots=True)
class FinanceAccountConfig:
    account_id: str
    display_name: str
    institution: str
    account_type: AccountType
    masked_identifier: str
    parser_profile: str
    statement_cadence: str
    source_intake_location: str
    output_workbook: str
    output_target: str
    reviewer: str
    status: AccountStatus = AccountStatus.PILOT
    date_tolerance_days: int = 3
    currency: str = "USD"

    def __post_init__(self) -> None:
        required = {
            "account_id": self.account_id,
            "display_name": self.display_name,
            "institution": self.institution,
            "masked_identifier": self.masked_identifier,
            "parser_profile": self.parser_profile,
            "statement_cadence": self.statement_cadence,
            "source_intake_location": self.source_intake_location,
            "output_workbook": self.output_workbook,
            "output_target": self.output_target,
            "reviewer": self.reviewer,
            "currency": self.currency,
        }
        missing = sorted(name for name, value in required.items() if not str(value).strip())
        if missing:
            raise ValueError("finance account fields are empty: " + ", ".join(missing))
        if self.date_tolerance_days < 0 or self.date_tolerance_days > 31:
            raise ValueError("date_tolerance_days must be between 0 and 31")
        if len(re.findall(r"\d", self.masked_identifier)) > 4:
            raise ValueError("masked_identifier may expose at most four digits")


@dataclass(frozen=True, slots=True)
class StatementHeader:
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    page_count: int
    currency: str = "USD"
    declared_increase_total: Decimal | None = None
    declared_decrease_total: Decimal | None = None

    def __post_init__(self) -> None:
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if self.page_count < 1:
            raise ValueError("page_count must be >= 1")
        if not self.currency.strip():
            raise ValueError("currency is required")
        for value in (self.declared_increase_total, self.declared_decrease_total):
            if value is not None and value < 0:
                raise ValueError("declared statement totals cannot be negative")


@dataclass(frozen=True, slots=True)
class StatementTransaction:
    transaction_id: str
    posted_date: date
    description: str
    amount: Decimal
    effect: BalanceEffect
    source: SourceLocation
    transaction_date: date | None = None
    reference: str | None = None
    normalized_payee: str | None = None

    def __post_init__(self) -> None:
        if not self.transaction_id.strip():
            raise ValueError("transaction_id is required")
        if not self.description.strip():
            raise ValueError("description is required")
        if self.amount <= 0:
            raise ValueError("transaction amount must be positive")


@dataclass(frozen=True, slots=True)
class StatementExtraction:
    account_id: str
    source_document_sha256: str
    document_kind: DocumentKind
    header: StatementHeader
    transactions: tuple[StatementTransaction, ...]

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("account_id is required")
        if not _SHA256.fullmatch(self.source_document_sha256):
            raise ValueError("source_document_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    entry_id: str
    posted_date: date
    description: str
    amount: Decimal
    effect: BalanceEffect
    reference: str | None = None

    def __post_init__(self) -> None:
        if not self.entry_id.strip():
            raise ValueError("entry_id is required")
        if not self.description.strip():
            raise ValueError("description is required")
        if self.amount <= 0:
            raise ValueError("ledger amount must be positive")
