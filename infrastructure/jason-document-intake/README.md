# Jason Document Intake — shared read-only boundary

**Status:** isolated development PR; not deployed, not production-accepted.
**Scope:** bounded PDF classification, native-text extraction, SHA-256,
document/page inventory and normalized source provenance. No business logic.

## Why this exists

Teams invoice/quote procurement and Lori's planned account/credit-card statement
reconciliation must use the *same PDF intake implementation*. Application
workflows must not copy PDF downloading, classification or extraction code
into their own finance/procurement parsers.

This module is the shared intake **service boundary** implemented as a reusable
Node module for the current Teams gateway. A standalone governed service/API
may be added when more consumers need remote access. Do not expose an
unauthenticated public parsing endpoint.

## Flow

1. A **provider-specific, already authorized** connector acquires the source
   document (Teams, approved mailbox, SharePoint or explicitly supplied file).
   Authentication, tenant scoping, permission checks and safe URL/redirect policy
   belong to the connector. Document Intake does not fetch URLs.
2. The caller enforces streaming size limits, then sends immutable PDF bytes
   into the shared inspector.
3. Shared intake validates PDF signature, configurable limits and page count;
   rejects encrypted/invalid documents; hashes bytes; invokes the existing
   Poppler pdfinfo, pdfimages -list, and pdftotext -layout tools; and
   reports classification and provenance with a versioned response.
4. A consumer adapter applies domain-specific rules. The procurement projection
   produces the **unchanged** Teams invoice ingress schema, without
   creating a second extraction path.
5. Finance reconciliation later consumes the **same versioned evidence schema**
   as an input to a separate statement parser/ledger matching flow. See
   #403 / draft #692 and TODO-FIN-003 / #1030. No QuickBooks API or accounting
   changes are authorized by this component.

## Evidence contract — jason.document_intake.pdf.v1

Fields:
- schema, source_sha256, size_bytes, page_count
- document_kind: native_text, hybrid, or scanned
- has_native_text, has_images, pages (optional page image inventory;
  per-page native-text presence is currently unknown)
- extracted_text: native Poppler text only; never silently truncated
- extraction_complete: true only when entire output is within limits
- rendered_verified: **false** (page rendering is not implemented)
- accounting_validated: **false** (not a reconciliation conclusion)

The record is an extraction and provenance *observation*, not a certification
of visible-page completeness. It must never be treated as proof that all charges
or balances were captured. Original statement bytes should be retained only
by the separately approved document evidence store, with permission controls,
retention policy, and masked/sensitive account identifier handling.

## Explicit exclusions

- OCR, page rendering/visual QA, scanned statement transcription.
- Bank or credit-card access, direct QuickBooks access, accounting writes.
- Invoice amount/category decisions, PO approvals, final reconciliation close.
- Common workflow or authority model: existing procurement and reconciliation
  each retain their separate, governed downstream states and controls.

**Fail-closed rules:** PDF missing/invalid/unreadable, encrypted, too many
pages, too large, text output over consumer limit or tool failure. Scanned
documents are classified; consumers requesting native text must reject them.
Additional visual/OCR processing must be separately built and accepted.

## Regression tests and rollout

The shared tests check strict limits, fingerprinting, page inventory,
text/scanned/hybrid classification, temporary-file cleanup, metadata
projection, no error text leaks and extraction with real Poppler tools.

Promotion requires the new shared CI and existing procurement/Teams tests
to pass; then a controlled end-to-end Teams invoice acceptance test,
followed by a finance pilot with one historically completed bank or card
statement and independently verified statement totals. Neither outcome is
implied by isolated unit tests.

**Multi-tenant principle:** no shared cross-customer cache, credentials,
document content persistence or implicit tenant context. Every provider
adapter must supply explicit scope/authority and preserve tenant-qualified
provenance through later evidence storage.

## Consumer routing matrix (planned and current)

| Consumer | Shared intake | Domain-specific validation | Activation |
| --- | --- | --- | --- |
| Teams invoices | Native-text PDF evidence adapter | Procurement document normalization, spending approval and Autotask checks | Existing production path replaced only after separate acceptance |
| Vendor quotes | Same Teams PDF evidence adapter | Quote/PO workflow and required line validation | Existing production path replaced only after separate acceptance |
| Bank statements | Versioned evidence supplied to the finance adapter | Full page visual proof, balances, bank transaction rules | Not activated |
| Credit-card statements | Same finance intake evidence | Payment/credit/fee separation, per-cardholder matching | Not activated |
| Other financial documents | New authorized acquisition adapter only | Document-type-specific rules and policy | Not activated |

Never activate an accounting consumer merely because shared PDF preflight succeeds.
The final accounting system remains governed QuickBooks Online, not the PDF
intake component or the temporary historical comparison spreadsheet.

## Optional scanned-document OCR adapter (engineering only)

`ocr-fallback.mjs` provides an **opt-in**, read-only page-rendering plus Tesseract OCR adapter. It verifies byte-source SHA-256 and page-count evidence, caps document size/page count/text volume, preserves page identity, uses temporary mode-0600 source bytes, and fails closed when rendering/OCR is unavailable. OCR text is always unverified evidence and **must never authorize or certify accounting reconciliation** without row/amount/date/account corroboration. The standard deployed Teams container and the Jason development host have not been verified to include Tesseract; no automatic runtime invocation, dependency installation or production activation is introduced by this branch. Integrating the OCR adapter into a governed consumer and visually validating scanned PDFs remain separate acceptance gates. Tests use controlled execution mocks rather than claim real Tesseract acceptance.
