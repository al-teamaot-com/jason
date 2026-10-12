"""Finance consumer of the shared Jason Document Intake evidence contract.

Does not parse PDFs, perform OCR, render pages, invoke tools, or access providers.
The shared PDF intake implementation is the sole preflight/extraction service.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from .adapters import PdfDocumentFacts
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
        if page_facts:
            if len(page_facts) != page_count:
                raise ValueError("incomplete page inventory")
            for index, record in enumerate(page_facts, 1):
                if not isinstance(record, Mapping) or record.get("page_number") != index:
                    raise ValueError("invalid page order")
                if type(record.get("image_count")) is not int or record["image_count"] < 0:
                    raise ValueError("invalid per-page image count")
                if record.get("native_text_present") is not None:
                    raise ValueError("shared intake cannot assert per-page text presence")

        # Per-page text was not proven in shared v1; do not manufacture page
        # claims or mark the statement verified. A later visual QA stage is
        # required before any financial transaction is accepted.
        return PdfDocumentFacts(
            document_sha256=digest,
            page_count=page_count,
            document_kind=kind,
            has_native_text=native,
            has_images=images,
        )
