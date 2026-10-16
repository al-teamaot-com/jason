"""Finance consumer of the shared Jason Document Intake evidence contract.

Does not parse PDFs, perform OCR, render pages, invoke tools, or access providers.
The shared PDF intake implementation is the sole preflight/extraction service.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from .adapters import PdfDocumentFacts, PdfPageFacts
from .contracts import DocumentKind


@dataclass(frozen=True, slots=True)
class SharedDocumentIntakeEvidenceAdapter:
    """Validate the shared service's output against immutable source PDF bytes."""

    max_pdf_bytes: int = 25_000_000
    max_pages: int = 200

    def __post_init__(self) -> None:
        if self.max_pdf_bytes < 1 or self.max_pages < 1:
            raise ValueError("document intake limits must be positive")

    def accept(self, document: bytes, evidence: Mapping[str, Any]) -> PdfDocumentFacts:
        if not isinstance(document, bytes) or not document.startswith(b"%PDF-"):
            raise ValueError("original immutable PDF bytes required")
        if len(document) > self.max_pdf_bytes:
            raise ValueError("PDF exceeds configured byte limit")
        if not isinstance(evidence, Mapping):
            raise ValueError("shared document evidence is required")
        if evidence.get("schema") != "jason.document_intake.pdf.v1":
            raise ValueError("unsupported document evidence schema")
        if evidence.get("extraction_complete") is not True:
            raise ValueError("incomplete shared document extraction")
        if evidence.get("rendered_verified") is not False or evidence.get("accounting_validated") is not False:
            raise ValueError("PDF preflight cannot assert accounting or visual verification")
        digest = sha256(document).hexdigest()
        if evidence.get("source_sha256") != digest or evidence.get("size_bytes") != len(document):
            raise ValueError("shared evidence does not match PDF bytes")
        page_count = evidence.get("page_count")
        if type(page_count) is not int or not 1 <= page_count <= self.max_pages:
            raise ValueError("invalid document page count")
        try:
            kind = DocumentKind(evidence["document_kind"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("unsupported document classification") from exc
        native = evidence.get("has_native_text")
        images = evidence.get("has_images")
        if type(native) is not bool or type(images) is not bool:
            raise ValueError("document content flags must be boolean")
        expected = (
            DocumentKind.HYBRID if native and images else
            DocumentKind.NATIVE_TEXT if native else
            DocumentKind.SCANNED if images else None
        )
        if expected is None or kind is not expected:
            raise ValueError("inconsistent document classification")
        text = evidence.get("extracted_text")
        if not isinstance(text, str) or bool(text.strip()) != native:
            raise ValueError("native-text claim is inconsistent")
        page_facts = evidence.get("pages", ())
        if not isinstance(page_facts, (list, tuple)):
            raise ValueError("invalid page inventory")
        verified_pages: list[PdfPageFacts] = []
        if page_facts:
            if len(page_facts) != page_count:
                raise ValueError("incomplete page inventory")
            for index, record in enumerate(page_facts, 1):
                if not isinstance(record, Mapping) or type(record.get("page_number")) is not int or record["page_number"] != index:
                    raise ValueError("invalid page order")
                image_count = record.get("image_count")
                if type(image_count) is not int or image_count < 0:
                    raise ValueError("invalid per-page image count")
                present = record.get("native_text_present")
                text_chars = record.get("native_text_chars")
                if present is None and text_chars is None:
                    # Unknown per-page text proof is not a false claim.
                    continue
                if type(present) is not bool or type(text_chars) is not int or text_chars < 0:
                    raise ValueError("inconsistent per-page native text facts")
                if present != (text_chars > 0):
                    raise ValueError("inconsistent per-page native text facts")
                verified_pages.append(PdfPageFacts(
                    page_number=index,
                    has_native_text=present,
                    native_text_chars=text_chars,
                    image_count=image_count,
                ))
        # Only expose a *complete* page inventory; partial evidence is not
        # equivalent to verified page coverage. This is not visual verification.
        if len(verified_pages) == page_count:
            if any(page.has_native_text for page in verified_pages) != native:
                raise ValueError("per-page text evidence contradicts document")
            if any(page.image_count > 0 for page in verified_pages) != images:
                raise ValueError("per-page image evidence contradicts document")
            pages = tuple(verified_pages)
        else:
            pages = ()

        return PdfDocumentFacts(
            document_sha256=digest,
            page_count=page_count,
            document_kind=kind,
            has_native_text=native,
            has_images=images,
            pages=pages,
        )
