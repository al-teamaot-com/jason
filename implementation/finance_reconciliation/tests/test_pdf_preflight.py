from hashlib import sha256
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from finance_reconciliation.contracts import DocumentKind
from finance_reconciliation.pdf_preflight import PypdfPreflightAdapter


def text_pdf():
    out = BytesIO()
    doc = canvas.Canvas(out)
    doc.drawString(50, 700, "Statement ending balance 100.00")
    doc.showPage()
    doc.save()
    return out.getvalue()


def test_text_document_is_fingerprinted_and_inventoried():
    raw = text_pdf()
    result = PypdfPreflightAdapter().inspect(raw)
    assert result.document_sha256 == sha256(raw).hexdigest()
    assert result.page_count == 1
    assert result.document_kind is DocumentKind.NATIVE_TEXT
    assert result.has_native_text is True
    assert result.pages[0].native_text_chars > 0
    assert result.pages[0].page_number == 1


def test_non_pdf_and_blank_pdf_fail_closed():
    with pytest.raises(ValueError, match="not a PDF"):
        PypdfPreflightAdapter().inspect(b"not a statement")
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=500)
    out = BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match="no detectable text or images"):
        PypdfPreflightAdapter().inspect(out.getvalue())


def test_rejects_encrypted_pdf_without_unlocking():
    reader = PdfReader(BytesIO(text_pdf()))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt("test-password")
    out = BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match="encrypted PDFs"):
        PypdfPreflightAdapter().inspect(out.getvalue())


def test_rejects_over_limit_before_parse():
    with pytest.raises(ValueError, match="byte limit"):
        PypdfPreflightAdapter(max_pdf_bytes=10).inspect(text_pdf())
    with pytest.raises(ValueError, match="page limit"):
        PypdfPreflightAdapter(max_pages=0 + 1).inspect(two_page_pdf())


def two_page_pdf():
    out = BytesIO()
    doc = canvas.Canvas(out)
    for number in (1, 2):
        doc.drawString(50, 700, "Page " + str(number))
        doc.showPage()
    doc.save()
    return out.getvalue()


def test_immutable_input_contract():
    with pytest.raises(TypeError, match="immutable"):
        PypdfPreflightAdapter().inspect(bytearray(text_pdf()))


def test_truncated_pdf_fails_closed():
    with pytest.raises(ValueError, match="PDF preflight failed"):
        PypdfPreflightAdapter().inspect(text_pdf()[:60])
