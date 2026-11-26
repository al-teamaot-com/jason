"""Original-bytes ChatGPT document handoff, no live provider calls."""
from base64 import b64encode
from hashlib import sha256
from io import BytesIO

import pytest
openpyxl = pytest.importorskip("openpyxl")
from connectors.constant_contact.intake_handoff import verify_excel_handoff
from connectors.constant_contact.xlsx_preflight import WorkbookPreflightError


def source(rows, *, filename="aot-import.xlsx", sheet_count=1):
    wb = openpyxl.Workbook()
    wb.active.append(("email", "marketing_consent", "consent_evidence"))
    for row in rows:
        wb.active.append(row)
    if sheet_count > 1:
        wb.create_sheet("Second")
    data = BytesIO()
    wb.save(data)
    raw = data.getvalue()
    return {
        "workbook_base64": b64encode(raw).decode("ascii"),
        "source_sha256": sha256(raw).hexdigest(),
        "source_reference": "chatgpt:attachment:12-abc",
        "filename": filename,
    }


def test_valid_handoff_proves_original_file_not_approval():
    args = source([("test@example.com", "explicit", "signed consent form")])
    evidence = verify_excel_handoff(**args)
    assert evidence.source_sha256 == args["source_sha256"]
    assert evidence.contact_count == 1
    assert evidence.workbook.startswith(b"PK")


@pytest.mark.parametrize("mutation", [
    {"source_sha256": "0" * 64},
    {"filename": "../unsafe.xlsx"},
    {"filename": "unsafe.xlsm"},
    {"source_reference": "../bad"},
    {"workbook_base64": "not-base64"},
])
def test_corrupt_or_unsupported_handoff_rejected(mutation):
    args = source([("test@example.com", "explicit", "signed consent form")])
    args.update(mutation)
    with pytest.raises(WorkbookPreflightError):
        verify_excel_handoff(**args)


@pytest.mark.parametrize("rows", [
    [("test@example.com", "explicit", "receipt"),
     ("test@example.com", "explicit", "receipt")],
    [("test@example.com", "explicit", "receipt"),
     ("second@example.com", "", "")],
    [("test@example.com", "explicit", "receipt")] * 26,
])
def test_invalid_duplicate_or_oversized_pilot_rejected(rows):
    with pytest.raises(WorkbookPreflightError):
        verify_excel_handoff(**source(rows))


def test_formula_or_multiple_sheets_rejected():
    with pytest.raises(WorkbookPreflightError):
        verify_excel_handoff(**source([("test@example.com", "explicit", "=1+2")]))
    with pytest.raises(WorkbookPreflightError):
        verify_excel_handoff(**source([("test@example.com", "explicit", "receipt")], sheet_count=2))


def test_zip_bomb_and_external_archive_parts_rejected():
    from zipfile import ZipFile, ZIP_DEFLATED
    for entries in (
        {"[Content_Types].xml": b"x", "xl/workbook.xml": b"z" * 10_000_000},
        {"[Content_Types].xml": b"x", "xl/workbook.xml": b"x",
         "xl/externalLinks/externalLink1.xml": b"x"},
        {"[Content_Types].xml": b"x", "xl/workbook.xml": b"x",
         "xl/_rels/workbook.xml.rels":
             b'<Relationship TargetMode="External" Target="https://invalid.example"/>'},
    ):
        stream = BytesIO()
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        raw = stream.getvalue()
        args = {
            "workbook_base64": b64encode(raw).decode(),
            "source_sha256": sha256(raw).hexdigest(),
            "source_reference": "chatgpt:attachment:malformed",
            "filename": "bad.xlsx",
        }
        with pytest.raises(WorkbookPreflightError):
            verify_excel_handoff(**args)
