from hashlib import sha256

import pytest

from finance_reconciliation.contracts import DocumentKind
from finance_reconciliation.pdf_preflight import SharedDocumentIntakeEvidenceAdapter


RAW = b"%PDF-1.4\nsynthetic-for-contract-testing-only"


def evidence(*, native=True, images=False, pages=None):
    return {
        "schema": "jason.document_intake.pdf.v1",
        "source_sha256": sha256(RAW).hexdigest(),
        "size_bytes": len(RAW),
        "page_count": 2,
        "document_kind": "hybrid" if native and images else "native_text" if native else "scanned",
        "has_native_text": native,
        "has_images": images,
        "pages": [] if pages is None else pages,
        "extracted_text": "Original statement text" if native else "",
        "extraction_complete": True,
        "rendered_verified": False,
        "accounting_validated": False,
    }


def test_finance_accepts_shared_pdf_evidence_without_reextracting():
    facts = SharedDocumentIntakeEvidenceAdapter().accept(RAW, evidence())
    assert facts.page_count == 2
    assert facts.document_kind is DocumentKind.NATIVE_TEXT
    assert facts.document_sha256 == sha256(RAW).hexdigest()
    assert facts.pages == ()  # Do not invent unverified per-page text facts.


def test_scanned_finance_pdf_preserves_missing_text_for_later_review():
    facts = SharedDocumentIntakeEvidenceAdapter().accept(RAW, evidence(native=False, images=True))
    assert facts.document_kind is DocumentKind.SCANNED
    assert facts.has_native_text is False


def test_stale_or_mismatched_bytes_fail_closed():
    bad = evidence()
    bad["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="does not match"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, bad)
    with pytest.raises(ValueError, match="immutable"):
        SharedDocumentIntakeEvidenceAdapter().accept(bytearray(RAW), evidence())


def test_unvalidated_or_mutated_accounting_assertions_fail_closed():
    bad = evidence()
    bad["extraction_complete"] = False
    with pytest.raises(ValueError, match="incomplete"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, bad)
    bad = evidence()
    bad["accounting_validated"] = True
    with pytest.raises(ValueError, match="cannot assert"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, bad)


def test_misclassified_and_unverified_pages_fail_closed():
    bad = evidence(native=False, images=True)
    bad["document_kind"] = "native_text"
    with pytest.raises(ValueError, match="inconsistent"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, bad)
    bad = evidence(pages=[
        {"page_number": 1, "image_count": 0, "native_text_present": None},
    ])
    with pytest.raises(ValueError, match="incomplete page inventory"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, bad)
    bad = evidence(pages=[
        {"page_number": 1, "image_count": 0, "native_text_present": True},
        {"page_number": 2, "image_count": 0, "native_text_present": None},
    ])
    with pytest.raises(ValueError, match="cannot assert per-page"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, bad)


def test_unsupported_shared_contract_rejected():
    bad = evidence()
    bad["schema"] = "jason.document_intake.pdf.v2"
    with pytest.raises(ValueError, match="unsupported"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, bad)


def test_mixed_scanned_page_inventory_is_preserved_for_visual_review():
    e = evidence(native=True, images=True, pages=[
        {"page_number": 1, "image_count": 0, "native_text_present": True, "native_text_chars": 20},
        {"page_number": 2, "image_count": 1, "native_text_present": False, "native_text_chars": 0},
    ])
    facts = SharedDocumentIntakeEvidenceAdapter().accept(RAW, e)
    assert len(facts.pages) == 2
    assert facts.pages[0].has_native_text is True
    assert facts.pages[1].has_native_text is False
    assert facts.pages[1].image_count == 1


def test_partial_page_text_coverage_is_unknown_not_verified():
    e = evidence(native=True, images=True, pages=[
        {"page_number": 1, "image_count": 0, "native_text_present": None, "native_text_chars": None},
        {"page_number": 2, "image_count": 1, "native_text_present": True, "native_text_chars": 10},
    ])
    facts = SharedDocumentIntakeEvidenceAdapter().accept(RAW, e)
    assert facts.pages == ()


def test_per_page_text_must_agree_with_global_claims():
    e = evidence(native=True, images=False, pages=[
        {"page_number": 1, "image_count": 0, "native_text_present": False, "native_text_chars": 0},
        {"page_number": 2, "image_count": 0, "native_text_present": False, "native_text_chars": 0},
    ])
    with pytest.raises(ValueError, match="contradicts"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, e)
    e["pages"][0]["native_text_present"] = True
    with pytest.raises(ValueError, match="inconsistent"):
        SharedDocumentIntakeEvidenceAdapter().accept(RAW, e)
