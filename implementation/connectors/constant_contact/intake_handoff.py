"""Bounded ChatGPT attachment-to-Jason XLSX handoff; never grants import authority.

The original attachment bytes are required, rather than trusting extracted rows.
Only an authenticated, separately authorized workflow may call a provider.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass

from .xlsx_preflight import MAX_WORKBOOK_BYTES, WorkbookPreflightError, preview_xlsx

_SHA = re.compile(r"^[0-9a-f]{64}$")
_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")


@dataclass(frozen=True)
class VerifiedExcelHandoff:
    workbook: bytes
    source_sha256: str
    source_reference: str
    filename: str
    contact_count: int


def verify_excel_handoff(
    *, workbook_base64: str, source_sha256: str,
    source_reference: str, filename: str,
) -> VerifiedExcelHandoff:
    """Validate original artifact and preflight before provider or approval work."""
    if (not isinstance(filename, str) or not filename.lower().endswith(".xlsx")
            or "/" in filename or "\\" in filename or len(filename) > 128
            or not isinstance(source_reference, str)
            or not _SOURCE.fullmatch(source_reference)
            or not isinstance(source_sha256, str) or not _SHA.fullmatch(source_sha256)
            or not isinstance(workbook_base64, str)
            or len(workbook_base64) > ((MAX_WORKBOOK_BYTES + 2) // 3) * 4 + 4):
        raise WorkbookPreflightError("Invalid authenticated workbook handoff metadata")
    try:
        workbook = base64.b64decode(workbook_base64, validate=True)
    except (binascii.Error, ValueError):
        raise WorkbookPreflightError("Invalid workbook encoding") from None
    if not 0 < len(workbook) <= MAX_WORKBOOK_BYTES:
        raise WorkbookPreflightError("Workbook size invalid")
    if hashlib.sha256(workbook).hexdigest() != source_sha256:
        raise WorkbookPreflightError("Workbook hash mismatch")
    if not workbook.startswith(b"PK\x03\x04"):
        raise WorkbookPreflightError("XLSX archive header invalid")
    preview = preview_xlsx(workbook)
    if preview.rejected or not 1 <= len(preview.accepted) <= 25:
        raise WorkbookPreflightError("Workbook is not eligible for the 25-contact pilot")
    return VerifiedExcelHandoff(
        workbook=workbook, source_sha256=source_sha256,
        source_reference=source_reference, filename=filename,
        contact_count=len(preview.accepted),
    )
