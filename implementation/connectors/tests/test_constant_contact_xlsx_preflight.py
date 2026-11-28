from io import BytesIO

import pytest
Workbook = pytest.importorskip("openpyxl").Workbook

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


def _rewrite_part(data, part, rewrite):
    from zipfile import ZipFile, ZIP_DEFLATED
    stream = BytesIO()
    with ZipFile(BytesIO(data)) as original, ZipFile(stream, "w", compression=ZIP_DEFLATED) as result:
        found = False
        for entry in original.infolist():
            content = original.read(entry.filename)
            if entry.filename == part:
                changed = rewrite(content)
                assert changed != content, part
                content = changed
                found = True
            result.writestr(entry.filename, content)
        assert found
    return stream.getvalue()


def test_underreported_dimensions_do_not_hide_unconsented_contact():
    data = workbook_bytes(HEADERS, [
        ["one@example.com", "explicit", "receipt", "One"],
        ["two@example.com", "", "", "Two"],
    ])
    data = _rewrite_part(data, "xl/worksheets/sheet1.xml",
                         lambda xml: xml.replace(b'<dimension ref="A1:D3"',
                                                 b'<dimension ref="A1:D2"'))
    result = preview_xlsx(data)
    assert len(result.accepted) == 1
    assert len(result.rejected) == 1
    assert result.rejected[0]["reason"] == "explicit_marketing_consent_not_documented"


def test_underreported_dimensions_do_not_hide_formula_column():
    data = workbook_bytes(HEADERS, [
        ["one@example.com", "explicit", "receipt", "One", "=2+2"],
    ])
    data = _rewrite_part(data, "xl/worksheets/sheet1.xml",
                         lambda xml: xml.replace(b'<dimension ref="A1:E2"',
                                                 b'<dimension ref="A1:D2"'))
    with pytest.raises(WorkbookPreflightError):
        preview_xlsx(data)


def test_external_relationship_with_xml_whitespace_is_denied():
    from connectors.constant_contact.xlsx_preflight import _check_archive_safety
    data = workbook_bytes(HEADERS, [["one@example.com", "explicit", "receipt", "One"]])
    data = _rewrite_part(data, "xl/_rels/workbook.xml.rels",
        lambda xml: xml.replace(b"</Relationships>",
            b'<Relationship Id="external-test" Type="urn:fixture" Target="https://invalid.example/" TargetMode = "External"/></Relationships>'))
    with pytest.raises(WorkbookPreflightError, match="external relationships"):
        _check_archive_safety(data)


@pytest.mark.parametrize("mode", [
    'TargetMode="External"',
    "TargetMode = 'External'",
    'TargetMode="Ext&#101;rnal"',
    'TargetMode="external"',
    'TargetMode="UnknownMode"',
])
def test_relationship_modes_are_parsed_not_substring_matched(mode):
    from connectors.constant_contact.xlsx_preflight import _check_relationship_xml
    xml = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
           '<Relationship Id="r1" Type="urn:fixture" Target="fixture" '+mode+'/>'
           '</Relationships>')
    for encoding in ("utf-8", "utf-16"):
        with pytest.raises(WorkbookPreflightError, match="external relationships"):
            _check_relationship_xml(xml.encode(encoding))


def test_relationship_xml_rejects_dtd_entities_and_malformed_document():
    from connectors.constant_contact.xlsx_preflight import _check_relationship_xml
    for xml in (
        b'<!DOCTYPE Relationships [<!ENTITY mode "External">]><Relationships/>',
        b'<!DOCTYPE Relationships SYSTEM "file:///synthetic-no-read"><Relationships/>',
        b'<Relationships>',
    ):
        with pytest.raises(WorkbookPreflightError, match="relationship XML"):
            _check_relationship_xml(xml)


def test_relationship_xml_accepts_internal_and_default_relationships():
    from connectors.constant_contact.xlsx_preflight import _check_relationship_xml
    _check_relationship_xml(b'<Relationships><Relationship Target="styles.xml" TargetMode="Internal"/><Relationship Target="theme/theme1.xml"/></Relationships>')


def test_underreported_dimension_does_not_bypass_physical_row_bound(monkeypatch):
    from connectors.constant_contact import xlsx_preflight as module
    monkeypatch.setattr(module, "MAX_CONTACTS", 3)
    data = workbook_bytes(HEADERS, [["one@example.com", "explicit", "receipt", "One"]])
    def move_row(xml):
        return xml.replace(b'<row r="2"', b'<row r="5"').replace(b'r="A2"', b'r="A5"').replace(b'r="B2"', b'r="B5"').replace(b'r="C2"', b'r="C5"').replace(b'r="D2"', b'r="D5"')
    data = _rewrite_part(data, "xl/worksheets/sheet1.xml", move_row)
    with pytest.raises(WorkbookPreflightError, match="rows or columns exceed bounds"):
        preview_xlsx(data)


def test_underreported_dimension_does_not_bypass_column_bound(monkeypatch):
    from connectors.constant_contact import xlsx_preflight as module
    monkeypatch.setattr(module, "MAX_COLUMNS", 4)
    data = workbook_bytes(HEADERS, [["one@example.com", "explicit", "receipt", "One"]])
    data = _rewrite_part(data, "xl/worksheets/sheet1.xml",
                         lambda xml: xml.replace(b'r="D2"', b'r="Z2"'))
    with pytest.raises(WorkbookPreflightError, match="rows or columns exceed bounds"):
        preview_xlsx(data)


def test_underreported_dimension_does_not_ignore_unapproved_column():
    data = workbook_bytes(HEADERS, [["one@example.com", "explicit", "receipt", "One", "unapproved"]])
    data = _rewrite_part(data, "xl/worksheets/sheet1.xml",
                         lambda xml: xml.replace(b'<dimension ref="A1:E2"', b'<dimension ref="A1:D2"'))
    with pytest.raises(WorkbookPreflightError, match="without approved headers"):
        preview_xlsx(data)
