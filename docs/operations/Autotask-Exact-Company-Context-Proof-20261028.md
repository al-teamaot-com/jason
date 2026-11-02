# Autotask Stage A — exact company existence proof

**Purpose:** Fix a release-blocking authorization weakness in the merged Stage A
source without adding permissions or changing existing production.

## Live read-only finding, October 28, 2026

The existing governed Autotask MCP capability `service.company.read` returned
`status=succeeded` for both a known company and a deliberately non-existent
numeric company ID. For the non-existent company, `evidence.data.item` was
`null`. Thus a success status alone is **not proof that the requested company
exists**, and cannot authorize a derived one-minute OBSERVE client context.

## Source repair

`_contract_client_context_for_identity` now requires a valid
`evidence.data.item.id` exactly matching the positive requested company ID
before it evaluates a grant or creates an ephemeral client context. Reject
missing evidence, empty/null records, non-positive company IDs, boolean IDs,
and mismatched returned IDs. Existing exact authorization and non-AOT denial
rules are unchanged; no added provider permissions or reads are introduced.

## Readiness evidence and limits

- Exercised the actual Stage A MCP source and unit tests in an isolated,
  no-network, read-only container using a source bind and temporary
  in-memory test filesystem. Tests include positive exact-company proof,
  success-with-null negative, wrong-ID negative, client-bound mismatch
  denial, requester grants and time-entry read fail-closed behavior.
- Real company-name `contains` queries, exact company reads and
  company-filtered Contracts reads also succeeded separately through the
  existing live **governed read-only** Jason connector; those are provider
  shape/selector evidence, not successful execution of the new source.
- The existing released Stage A PM candidate SHA
  `1586dd9da10c23d7988d684a7c0b254c6353bef1` contains the
  status-only validation bug and **must not be deployed**.
- This fix must pass exact-source CI, be merged into protected main, and
  obtain a fresh Production Manager candidate SHA and all gate receipts.
- Technician-specific TimeEntries read remains disabled pending independently
  proved positive and negative provider authorization. Unproven IT Glue,
  Entra, Autotask write and client-notification capabilities remain separately
  governed/disabled as before.
- A passing unit suite or read-only existing production provider query does not
  prove the new candidate end-to-end provider authorization. Do not bypass the
  production freeze or owner exact-SHA deployment authorization.

## Concurrent source integration

Integration coordination: #2125 #2128 #2129 #2131. The MCP server
file overlaps routine read/write branches, but the source review merge-tree
showed clean non-overlapping portions. Reconcile after source merge; do not
overwrite other branches or activate deferred write capabilities.
