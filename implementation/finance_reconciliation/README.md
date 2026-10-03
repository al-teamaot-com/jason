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
