"""Read-only Excel intake and preview for future governed Constant Contact imports.

This module never sends contacts, obtains tokens, or authorizes an import.
Approval and provider adapters must be implemented in the shared Jason governance path.
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from typing import Any

MAX_FILE_BYTES = 4_000_000
MAX_ROWS = 40_000
MAX_COLUMNS = 60
MAX_UNCOMPRESSED_BYTES = 24_000_000
MAX_ZIP_MEMBERS = 200
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FIELD_ALIASES = {
    "email_address": {"email", "email address", "email_address", "e-mail", "e mail"},
    "first_name": {"first", "first name", "firstname", "given name"},
    "last_name": {"last", "last name", "lastname", "surname", "family name"},
    "company_name": {"company", "company name", "organization", "organisation"},
    "job_title": {"title", "job title", "position"},
    "phone_number": {"phone", "phone number", "telephone", "mobile"},
}
# Deliberately conservative: phone is NOT mapped until a verified CC payload contract exists.
SUPPORTED_FIELDS = frozenset({"email_address", "first_name", "last_name", "company_name", "job_title"})


class WorkbookValidationError(ValueError):
    """Unsafe, ambiguous, or unsupported workbook."""


@dataclass(frozen=True)
class RejectedRow:
    sheet_row: int
    reason: str


@dataclass(frozen=True)
class ImportPreview:
    sha256: str
    sheet_name: str
    total_rows: int
    accepted: tuple[dict[str, str], ...]
    rejected: tuple[RejectedRow, ...]
    mapping: dict[str, str]
    unmapped_columns: tuple[str, ...]

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)


def _heading(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def preview_xlsx(data: bytes, *, sheet_name: str | None = None) -> ImportPreview:
    """Parse an untrusted .xlsx to a non-authoritative, read-only import preview.

    Each accepted record includes a source row marker for later evidence binding.
    This function does NOT assert contact consent, existing-contact status,
    provider list membership, or approval to change any records.
    """
    if not isinstance(data, bytes) or not data or len(data) > MAX_FILE_BYTES:
        raise WorkbookValidationError("File must be nonempty .xlsx, no larger than 4 MB")
    if not data.startswith(b"PK"):
        raise WorkbookValidationError("Expected an .xlsx ZIP container")
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise WorkbookValidationError("Excel parser dependency openpyxl is unavailable") from exc

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_MEMBERS or sum(e.file_size for e in entries) > MAX_UNCOMPRESSED_BYTES:
                raise WorkbookValidationError("Workbook archive exceeds decompression limits")
            if any(
                e.filename.startswith(("xl/externalLinks/", "xl/embeddings/", "xl/activeX/"))
                or e.filename.lower().endswith((".bin", ".vba"))
                for e in entries
            ):
                raise WorkbookValidationError("External links, embedded objects and macros are not allowed")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise WorkbookValidationError("Invalid workbook archive") from exc
    digest = hashlib.sha256(data).hexdigest()
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
    except Exception as exc:
        raise WorkbookValidationError("Unable to parse .xlsx workbook") from exc

    try:
        if sheet_name is None:
            if len(workbook.sheetnames) != 1:
                raise WorkbookValidationError("Select a worksheet explicitly when there are multiple sheets")
            sheet_name = workbook.sheetnames[0]
        if sheet_name not in workbook.sheetnames:
            raise WorkbookValidationError("Specified worksheet does not exist")
        sheet = workbook[sheet_name]
        if sheet.max_row and sheet.max_row > MAX_ROWS + 1:
            raise WorkbookValidationError("Workbook exceeds configured row limit")
        if sheet.max_column and sheet.max_column > MAX_COLUMNS:
            raise WorkbookValidationError("Workbook exceeds configured column limit")
        iterator = sheet.iter_rows(values_only=False)
        header_cells = next(iterator, None)
        if not header_cells:
            raise WorkbookValidationError("Worksheet is empty")
        headers = [str(cell.value or "").strip() for cell in header_cells]
        if any(not heading for heading in headers):
            raise WorkbookValidationError("Every populated column must have a nonempty header")
        if len({_heading(h) for h in headers}) != len(headers):
            raise WorkbookValidationError("Duplicate column headers are ambiguous")
        mapping: dict[str, str] = {}
        for heading in headers:
            matches = [field for field, aliases in FIELD_ALIASES.items() if _heading(heading) in aliases]
            if len(matches) == 1 and matches[0] in SUPPORTED_FIELDS:
                if matches[0] in mapping.values():
                    raise WorkbookValidationError("Multiple columns map to the same contact field")
                mapping[heading] = matches[0]
        if "email_address" not in mapping.values():
            raise WorkbookValidationError("An Email column is required")
        rejected: list[RejectedRow] = []
        accepted: list[dict[str, str]] = []
        seen: set[str] = set()
        total_rows = 0
        for row_number, row in enumerate(iterator, start=2):
            if row_number > MAX_ROWS + 1:
                raise WorkbookValidationError("Workbook exceeds configured row limit")
            if all(cell.value is None for cell in row):
                continue
            total_rows += 1
            if any(cell.data_type == "f" for cell in row):
                rejected.append(RejectedRow(row_number, "Formula cells are not allowed"))
                continue
            values = [cell.value for cell in row]
            record = {
                field: str(values[headers.index(heading)]).strip()
                for heading, field in mapping.items()
                if headers.index(heading) < len(values)
                and values[headers.index(heading)] is not None
            }
            address = record.get("email_address", "").lower()
            if not EMAIL_RE.fullmatch(address) or len(address) > 254:
                rejected.append(RejectedRow(row_number, "Missing or invalid email"))
                continue
            if address in seen:
                rejected.append(RejectedRow(row_number, "Duplicate email within workbook"))
                continue
            seen.add(address)
            record["email_address"] = address
            record["_source_row"] = str(row_number)
            accepted.append(record)
        return ImportPreview(
            sha256=digest,
            sheet_name=sheet_name,
            total_rows=total_rows,
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            mapping=mapping,
            unmapped_columns=tuple(h for h in headers if h not in mapping),
        )
    finally:
        workbook.close()
