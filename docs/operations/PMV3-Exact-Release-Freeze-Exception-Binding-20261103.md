# PMV3: exact release freeze-exception binding (2026-11-03)

## Why this release candidate exists

An earlier protected-main candidate, `e330dc0e229a02e15f77f620ebc2a5c01d4a70d9`, passed preproduction and obtained an authenticated Teams release approval. Its existing prepared release record and manifest nevertheless omitted the already-declared `one_transaction_freeze_exception`. The native promotion correctly denied production because the distinct Owner-ordered `production-deployment-freeze` marker remained active. **No production mutation occurred.** A signed deploy approval alone cannot repair an approved record's missing freeze-exception binding.

## Governed disposition

The source's existing `config/production-deployment-freeze-exception.json` is renewed here to a short, finite expiry to allow **a new immutable candidate and fresh exact-SHA decision**. The declaration authorizes no action on its own. The exact candidate's release record and immutable manifest must BOTH include the source declaration before any Teams approval is solicited. The Owner approval must bind that exact purpose, SHA, rollback and reviewed scope. The native one-transaction freeze exception is permitted only through the approved `provider_identity_and_authority_recovery` profile and only when every required runtime/MCP/host/CCC/root/rollback control passes. The original freeze marker must be byte-identically restored after the deployment transaction, whether it succeeds or fails.

The frozen predecessor's already signed `e330...` record remains immutable and cannot be reused, reset, patched, or re-labeled. The global `unfreeze-release` workflow is a separate Owner decision; do not use it as a substitute for the source-bound, auto-restored one-transaction exception. Do not rewrite Owner approval sources or directly unlink the freeze marker.

## Acceptance requirements

1. The new source SHA descends from protected main, and protected CI passes.
2. Use the **exact new candidate** controller for fresh preparation, not the older installed LKG Release Manager; confirm `record.one_transaction_freeze_exception` and `release_manifest.one_transaction_freeze_exception` both equal the source declaration.
3. Repeat immutable preproduction, full impact/parallel-work review, and exact LKG rollback readiness.
4. Publish a **new** nonexecuting Teams Owner approval offer whose purpose includes the freeze exception. Explicitly authorized production deployment is a separate future action; no approval is implied here.
5. Native PMV3 promotion must independently enforce the one-time freeze exception, preserve source/Owner/CCC bindings, and restore the freeze marker. Do not deploy if the exception expires or any protected check fails.
6. Afterward, verify host, runtime, MCP, root drift, LKG, ticket/provider canaries, and frozen-state restoration. Only then return to PMV3 integration PR #2280 and KFS PR #2282.
