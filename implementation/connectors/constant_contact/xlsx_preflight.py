"""Read-only XLSX intake for Constant Contact contact import previews.

Workbook bytes are parsed locally. This does not issue provider calls or create
contacts. Import authority is never inferred from workbook data.
"""
from __future__ import annotations

from io import BytesIO
from typing import Mapping

from .import_preflight import ImportPreflight, preflight

MAX_WORKBOOK_BYTES = 4_000_000
MAX_CONTACTS = 39999
MAX_COLUMNS = 30
ALLOWED_COLUMNS = frozenset({
    "email", "first_name", "last_name", "company_name", "job_title",
    "marketing_consent", "consent_evidence",
})


class WorkbookPreflightError(ValueError):
    """Safe workbook validation error."""


def preview_xlsx(
    data: bytes, *,
    known_suppressed: set[str] | None = None,
    suppression_inventory_complete: bool = False,
) -> ImportPreflight:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_WORKBOOK_BYTES:
        raise WorkbookPreflightError("Workbook size invalid")
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise WorkbookPreflightError("XLSX reader dependency is unavailable") from None
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            if len(workbook.worksheets) != 1:
                raise WorkbookPreflightError("Exactly one worksheet is required")
            sheet = workbook.worksheets[0]
            if sheet.max_column > MAX_COLUMNS or sheet.max_row > MAX_CONTACTS + 1:
                raise WorkbookPreflightError("Workbook rows or columns exceed bounds")
            iterator = sheet.iter_rows(values_only=False)
            header_cells = next(iterator, None)
            if header_cells is None:
                raise WorkbookPreflightError("Workbook has no header")
            headers = [str(c.value or "").strip().lower() for c in header_cells]
            if len(headers) != len(set(headers)) or any(h not in ALLOWED_COLUMNS for h in headers):
                raise WorkbookPreflightError("Headers are duplicated or not approved")
            if not {"email", "marketing_consent", "consent_evidence"} <= set(headers):
                raise WorkbookPreflightError("Required contact and consent columns missing")
            rows: list[dict[str, object]] = []
            for cells in iterator:
                if any(c.data_type == "f" for c in cells):
                    raise WorkbookPreflightError("Workbook formulas are not permitted")
                values = [c.value for c in cells]
                if all(v is None or str(v).strip() == "" for v in values):
                    continue
                if len(rows) >= MAX_CONTACTS:
                    raise WorkbookPreflightError("Contact row limit exceeded")
                rows.append(dict(zip(headers, values)))
            return preflight(rows,
                             known_suppressed=known_suppressed,
                             suppression_inventory_complete=suppression_inventory_complete)
        finally:
            workbook.close()
    except WorkbookPreflightError:
        raise
    except Exception:
        raise WorkbookPreflightError("Workbook could not be processed safely") from None
