"""Preproduction tests for read-only Constant Contact Excel preview."""
import io
import unittest

from openpyxl import Workbook

from connectors.constant_contact.excel_preview import (
    WorkbookValidationError,
    preview_xlsx,
)


def workbook_bytes(rows, *, extra_sheet=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Contacts"
    for row in rows:
        sheet.append(row)
    if extra_sheet:
        workbook.create_sheet("Other")
    buf = io.BytesIO()
    workbook.save(buf)
    workbook.close()
    return buf.getvalue()


class ExcelPreviewTests(unittest.TestCase):
    def test_normalization_and_unknown_column(self):
        data = workbook_bytes([
            ["Email", "First Name", "Last Name", "Unrecognized"],
            [" Alice@Example.com ", "Alice", "Jones", "not imported"],
        ])
        result = preview_xlsx(data)
        self.assertEqual(result.total_rows, 1)
        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.accepted[0]["email_address"], "alice@example.com")
        self.assertEqual(result.accepted[0]["_source_row"], "2")
        self.assertEqual(result.unmapped_columns, ("Unrecognized",))
        self.assertEqual(len(result.sha256), 64)

    def test_invalid_and_duplicate_emails_rejected(self):
        data = workbook_bytes([
            ["Email", "First Name"],
            ["same@example.com", "One"],
            ["SAME@example.com", "Two"],
            ["missing-at-sign", "Three"],
            [None, "Four"],
        ])
        result = preview_xlsx(data)
        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(len(result.rejected), 3)
        self.assertEqual([r.sheet_row for r in result.rejected], [3, 4, 5])

    def test_formula_row_rejected(self):
        data = workbook_bytes([
            ["Email", "First Name"],
            ["ok@example.com", "=2+2"],
        ])
        result = preview_xlsx(data)
        self.assertEqual(result.accepted_count, 0)
        self.assertEqual(result.rejected[0].reason, "Formula cells are not allowed")

    def test_multisheet_requires_selection(self):
        data = workbook_bytes([["Email"], ["ok@example.com"]], extra_sheet=True)
        with self.assertRaisesRegex(WorkbookValidationError, "Select a worksheet"):
            preview_xlsx(data)
        result = preview_xlsx(data, sheet_name="Contacts")
        self.assertEqual(result.accepted_count, 1)

    def test_ambiguous_headers_rejected(self):
        data = workbook_bytes([
            ["Email", "E-mail"],
            ["one@example.com", "two@example.com"],
        ])
        with self.assertRaisesRegex(WorkbookValidationError, "map to the same"):
            preview_xlsx(data)

    def test_missing_email_header_rejected(self):
        data = workbook_bytes([["Name"], ["Alice"]])
        with self.assertRaisesRegex(WorkbookValidationError, "Email column"):
            preview_xlsx(data)

    def test_invalid_file_rejected(self):
        with self.assertRaises(WorkbookValidationError):
            preview_xlsx(b"not a workbook")


if __name__ == "__main__":
    unittest.main()
