"""Strict, read-only PDF intake for isolated finance reconciliation pilots.

This detects evidence available for later extraction. It does NOT parse financial
transactions, perform OCR, render pages, or certify statement completeness.
Original PDF bytes are never modified or persisted by this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader

from .adapters import PdfDocumentFacts, PdfPageFacts
from .contracts import DocumentKind


@dataclass(frozen=True, slots=True)
class PypdfPreflightAdapter:
    """Inventory a bounded PDF without accessing a provider or account.

    A PDF with any raster imagery is conservatively classified HYBRID when
    native text is also present: even a logo can trigger this classification.
    This deliberately favors follow-up visual inspection over assuming that
    every transaction was fully extracted as text.
    """

    max_pdf_bytes: int = 25_000_000
    max_pages: int = 200

    def __post_init__(self) -> None:
        if self.max_pdf_bytes <= 0 or self.max_pages <= 0:
            raise ValueError("PDF preflight limits must be positive")

    def inspect(self, document: bytes) -> PdfDocumentFacts:
        if not isinstance(document, bytes):
            raise TypeError("document must be immutable PDF bytes")
        if not document.startswith(b"%PDF-"):
            raise ValueError("document is not a PDF")
        if len(document) > self.max_pdf_bytes:
            raise ValueError("PDF exceeds configured byte limit")

        document_sha256 = sha256(document).hexdigest()
        try:
            reader = PdfReader(BytesIO(document), strict=True)
            if reader.is_encrypted:
                raise ValueError("encrypted PDFs require a separately approved intake flow")
            page_count = len(reader.pages)
            if page_count < 1:
                raise ValueError("PDF has no pages")
            if page_count > self.max_pages:
                raise ValueError("PDF exceeds configured page limit")

            inventory: list[PdfPageFacts] = []
            for page_index, page in enumerate(reader.pages, start=1):
                native_text = page.extract_text() or ""
                text_chars = len("".join(native_text.split()))
                image_count = len(page.images)
                inventory.append(
                    PdfPageFacts(
                        page_number=page_index,
                        has_native_text=text_chars > 0,
                        native_text_chars=text_chars,
                        image_count=image_count,
                    )
                )
        except ValueError:
            raise
        except Exception as exc:
            # Malformed financial documents cannot be silently normalized.
            # Do not expose extracted content or password-bearing internals.
            raise ValueError("PDF preflight failed; manual document review required") from exc

        has_native_text = any(page.has_native_text for page in inventory)
        has_images = any(page.image_count > 0 for page in inventory)
        if not has_native_text and not has_images:
            raise ValueError("PDF has no detectable text or images")

        kind = (
            DocumentKind.HYBRID
            if has_native_text and has_images
            else DocumentKind.NATIVE_TEXT
            if has_native_text
            else DocumentKind.SCANNED
        )
        return PdfDocumentFacts(
            document_sha256=document_sha256,
            page_count=page_count,
            document_kind=kind,
            has_native_text=has_native_text,
            has_images=has_images,
            pages=tuple(inventory),
        )
