from io import BytesIO

import pytest
from openpyxl import Workbook

from connectors.constant_contact.xlsx_preflight import WorkbookPreflightError, preview_xlsx


def workbook_bytes(headers, rows, extra_sheet=False):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    if extra_sheet:
        wb.create_sheet("Second")
    data = BytesIO()
    wb.save(data)
    return data.getvalue()


HEADERS = ["email", "marketing_consent", "consent_evidence", "first_name"]


def test_accepted_workbook_is_never_self_authorizing():
    result = preview_xlsx(workbook_bytes(HEADERS, [
        ["one@example.com", "explicit", "signed form receipt", "One"]
    ]), suppression_inventory_complete=True)
    assert [row["email"] for row in result.accepted] == ["one@example.com"]
    assert result.executable is False


def test_missing_consent_is_rejected():
    result = preview_xlsx(workbook_bytes(HEADERS, [
        ["one@example.com", "", "", "One"]
    ]))
    assert result.rejected[0]["reason"] == "explicit_marketing_consent_not_documented"


def test_formula_is_rejected():
    with pytest.raises(WorkbookPreflightError, match="formulas"):
        preview_xlsx(workbook_bytes(HEADERS, [
            ["one@example.com", "explicit", "receipt", "=2+2"]
        ]))


@pytest.mark.parametrize("headers,extra_sheet", [
    (["email", "email", "consent_evidence", "marketing_consent"], False),
    (["email", "unknown", "consent_evidence", "marketing_consent"], False),
    (HEADERS, True),
])
def test_bad_headers_or_multiple_sheets_rejected(headers, extra_sheet):
    with pytest.raises(WorkbookPreflightError):
        preview_xlsx(workbook_bytes(headers, [], extra_sheet=extra_sheet))


def test_too_large_raw_input_rejected():
    with pytest.raises(WorkbookPreflightError, match="size"):
        preview_xlsx(b"x" * 4_000_001)
