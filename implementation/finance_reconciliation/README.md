# Finance Reconciliation Foundation

This package is a non-production foundation for Project Jason issue #403.

## Current boundary

The package is intentionally **not registered with the Jason runtime** and has:

- no bank or credit-card connectivity
- no provider credentials
- no QuickBooks Online connectivity
- no Excel/SharePoint write capability
- no Teams send capability
- no production workflow registration
- no financial mutation capability

It is safe scaffolding for the first-account pilot.

## What is implemented

- configuration-driven finance account registry
- provider-neutral statement and transaction contracts
- source PDF provenance down to page/bounding-box level
- deterministic statement balance and declared-total validation
- conservative one-to-one ledger matching
- fail-closed ambiguous matching
- provider-neutral human-input request contract
- rerouting context for flows such as Lori replying "ask Arnold"

## Design principles

1. Accounts are configuration, not code.
2. Original statement evidence remains authoritative and immutable.
3. Financial extraction acceptance depends on deterministic proof, not AI/OCR confidence.
4. Ambiguous matching remains unresolved.
5. Human questions are created only when workflow input is required or during explicit testing.
6. Teams is a delivery channel for a bounded human-input request; this package does not create a general Teams conversation path.
7. Adding QuickBooks Online later should require an adapter to the canonical ledger-entry contract, not a rewrite of the reconciliation engine.

## Next implementation steps after Lori discovery

- add PDF preflight/render/extraction adapter interfaces
- implement the first real statement-format adapter from Lori's sample PDF
- add evidence-crop generation for ambiguous fields
- map Lori's Excel workbook to a governed workbook adapter
- add a QBO ledger adapter when QBO access is available
- connect bounded human-input requests to the existing Teams approval/continuation path
- add audit persistence and operational metrics
- run a historical completed period as the first acceptance test

## PDF preflight slice (2026-10-12)

The isolated `PypdfPreflightAdapter` performs a strict, read-only intake check:
PDF magic header, configurable byte/page limits, encryption rejection, SHA-256
fingerprinting, per-page native-text/image inventory, and conservative document
classification. The original PDF bytes are unchanged; empty and malformed PDFs
fail closed. The adapter does not use OCR or connect to any financial provider.

**Accounting boundary:** A readable PDF is *not* a reconciled statement. Preflight
does not verify page rendering, complete transaction extraction, opening/closing
balances, accounting classifications, or ledger matches. Those must pass later
independent, deterministic validation before any statement is accepted.

The synthetic unit tests cover valid native-text files, blank/non-PDF inputs,
encryption, size/page limits, immutable input, and truncation. The isolated CI
workflow installs `pypdf` and `reportlab` for these tests.

**Design alignment:** The existing workbook fields are legacy pilot scaffolding.
Per TODO-FIN-003's 2026-10-06 decision, Excel is a temporary comparison source,
not a required future write target or accounting system of record. QBO remains
subject to independent governed authorization; no QBO writes are permitted here.

## Shared document intake convergence (2026-10-12)

The earlier standalone Python/Pypdf PDF preflight was retired on this isolated
branch to prevent a second parser from diverging from the production Teams
invoice/quote implementation. The finance consumer now validates the canonical
`jason.document_intake.pdf.v1` evidence output supplied by the separate
shared Document Intake component (draft PR #1326).

The Python consumer verifies the original source bytes and SHA-256, extracted
size, page count, document class, completeness flags and any supplied image-page
inventory. It does **not** create unverified per-page native-text claims. These
facts do not constitute transaction extraction or statement reconciliation.

Integration with the shared intake runtime is not activated, and this draft
remains blocked on governed document acquisition, statement rendering/visual
verification, domain transaction parsing, and historical Lori acceptance. The
existing workbook contract is legacy pilot scaffolding; under TODO-FIN-003,
Excel is comparison-only once governed QBO access is usable.

### Merge sequencing and release gate

The shared-intake PR #1326 should be reviewed and accepted before any runtime
wiring from this finance foundation is enabled. This branch only validates the
same v1 evidence *record*; it does not call the shared Node component directly.
Actual transport must preserve source bytes and their hash, tenant/account
scope, and the existing governed finance authorization boundary. A mismatched
record must fail closed without attempting a second, silent extraction method.
