"""Adapter boundaries for future PDF, ledger, and workbook integrations.

These are contracts only. They perform no I/O and create no production access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from .contracts import (
    DocumentKind,
    FinanceAccountConfig,
    LedgerEntry,
    StatementExtraction,
)


@dataclass(frozen=True, slots=True)
class PdfDocumentFacts:
    document_sha256: str
    page_count: int
    document_kind: DocumentKind
    has_native_text: bool
    has_images: bool

    def __post_init__(self) -> None:
        if self.page_count < 1:
            raise ValueError("page_count must be >= 1")


@runtime_checkable
class PdfPreflightAdapter(Protocol):
    def inspect(self, document: bytes) -> PdfDocumentFacts:
        """Classify and inventory a PDF without changing it."""


@runtime_checkable
class StatementParserAdapter(Protocol):
    @property
    def profile_id(self) -> str:
        """Stable parser profile identifier used by account configuration."""

    def extract(
        self,
        *,
        document: bytes,
        account: FinanceAccountConfig,
        preflight: PdfDocumentFacts,
    ) -> StatementExtraction:
        """Extract canonical statement evidence with source provenance."""


@runtime_checkable
class LedgerSourceAdapter(Protocol):
    @property
    def source_id(self) -> str:
        """Stable source identifier, e.g. excel-ledger-v1 or qbo-v1."""

    def entries(
        self,
        *,
        account: FinanceAccountConfig,
        period_start: date,
        period_end: date,
    ) -> tuple[LedgerEntry, ...]:
        """Return canonical ledger evidence for reconciliation."""


@dataclass(frozen=True, slots=True)
class WorkbookSnapshot:
    workbook_id: str
    version: str
    target: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class WorkbookMutation:
    operation: str
    target: str
    values: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class WorkbookWritePlan:
    account_id: str
    expected_version: str
    mutations: tuple[WorkbookMutation, ...]


@runtime_checkable
class WorkbookAdapter(Protocol):
    def snapshot(self, *, account: FinanceAccountConfig) -> WorkbookSnapshot:
        """Read the current workbook version before planning a write."""

    def apply(
        self,
        *,
        account: FinanceAccountConfig,
        plan: WorkbookWritePlan,
    ) -> WorkbookSnapshot:
        """Apply a bounded plan and return a post-write snapshot for verification."""
