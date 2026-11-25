"""Read-only XLSX intake for Constant Contact contact import previews.

Workbook bytes are parsed locally. This does not issue provider calls or create
contacts. Import authority is never inferred from workbook data.
"""
from __future__ import annotations

from io import BytesIO
from typing import Mapping
import stat
from zipfile import ZipFile, BadZipFile
from xml.parsers import expat

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


def _check_relationship_xml(data: bytes) -> None:
    """Parse bounded package relationships without DTDs or entity expansion."""
    parser = expat.ParserCreate(namespace_separator="}")

    def deny_unsafe_xml(*_args):
        raise WorkbookPreflightError("Unsafe XLSX relationship XML")

    def check_element(_name, attributes):
        for key, value in attributes.items():
            if key.rsplit("}", 1)[-1].casefold() == "targetmode":
                if value.strip().casefold() != "internal":
                    raise WorkbookPreflightError("XLSX external relationships forbidden")

    parser.StartElementHandler = check_element
    parser.StartDoctypeDeclHandler = deny_unsafe_xml
    parser.EntityDeclHandler = deny_unsafe_xml
    parser.ExternalEntityRefHandler = deny_unsafe_xml
    try:
        parser.Parse(data, True)
    except expat.ExpatError:
        raise WorkbookPreflightError("Invalid XLSX relationship XML") from None


def _check_archive_safety(data: bytes) -> None:
    """Reject zip bombs, external relations, embedded content and unsafe paths.

    Source files are untrusted, and a 4-MB compressed workbook can otherwise
    inflate to a very large amount of XML before any contact-row limits apply.
    """
    try:
        with ZipFile(BytesIO(data)) as archive:
            parts = archive.infolist()
            if not 1 <= len(parts) <= 128:
                raise WorkbookPreflightError("XLSX archive member count invalid")
            seen: set[str] = set()
            total = 0
            for info in parts:
                name = info.filename
                lowered = name.casefold()
                if (name in seen or name.startswith("/")
                        or "\\" in name
                        or any(bit in ("", "..") for bit in name.split("/")[:-1])
                        or info.flag_bits & 1
                        or stat.S_ISLNK(info.external_attr >> 16)
                        or any(blocked in lowered for blocked in (
                            "vba", "externallinks/", "activex/", "embeddings/",
                            "connections.xml", "querytables/",
                        ))):
                    raise WorkbookPreflightError("Unsafe XLSX archive content")
                seen.add(name)
                total += info.file_size
                if (info.file_size > 8_000_000 or total > 16_000_000
                        or (info.file_size > 2048
                            and info.file_size / max(1, info.compress_size) > 100)):
                    raise WorkbookPreflightError("XLSX decompression limits exceeded")
                if lowered.endswith(".rels"):
                    _check_relationship_xml(archive.read(info, pwd=None))
            if "[Content_Types].xml" not in seen or "xl/workbook.xml" not in seen:
                raise WorkbookPreflightError("XLSX required package parts missing")
    except WorkbookPreflightError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError):
        raise WorkbookPreflightError("Workbook archive invalid") from None


def preview_xlsx(
    data: bytes, *,
    known_suppressed: set[str] | None = None,
    suppression_inventory_complete: bool = False,
) -> ImportPreflight:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_WORKBOOK_BYTES:
        raise WorkbookPreflightError("Workbook size invalid")
    _check_archive_safety(data)
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
            if ((sheet.max_column is not None and sheet.max_column > MAX_COLUMNS)
                    or (sheet.max_row is not None and sheet.max_row > MAX_CONTACTS + 1)):
                raise WorkbookPreflightError("Workbook rows or columns exceed bounds")
            # Worksheet dimensions are supplied by the workbook and can
            # truncate real rows/cells in openpyxl read-only mode. Inspect the
            # actual row stream; enforce physical row and column limits below.
            sheet.reset_dimensions()
            iterator = sheet.iter_rows(values_only=False)
            header_cells = next(iterator, None)
            if not header_cells:
                raise WorkbookPreflightError("Workbook has no header")
            if len(header_cells) > MAX_COLUMNS:
                raise WorkbookPreflightError("Workbook rows or columns exceed bounds")
            headers = [str(c.value or "").strip().lower() for c in header_cells]
            if len(headers) != len(set(headers)) or any(h not in ALLOWED_COLUMNS for h in headers):
                raise WorkbookPreflightError("Headers are duplicated or not approved")
            if not {"email", "marketing_consent", "consent_evidence"} <= set(headers):
                raise WorkbookPreflightError("Required contact and consent columns missing")
            rows: list[dict[str, object]] = []
            for row_number, cells in enumerate(iterator, start=2):
                if row_number > MAX_CONTACTS + 1 or len(cells) > MAX_COLUMNS:
                    raise WorkbookPreflightError("Workbook rows or columns exceed bounds")
                if any(c.data_type == "f" for c in cells):
                    raise WorkbookPreflightError("Workbook formulas are not permitted")
                if len(cells) > len(headers):
                    raise WorkbookPreflightError("Workbook contains columns without approved headers")
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
