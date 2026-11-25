# Deterministic accounting reconciliation foundation

## Scope

A non-activated, read-only engine for comparing already normalized statement and ledger entries, intended for the Lori bank/credit-card reconciliation workflow in #403 and the Kaseya-first vendor/billing matching workstream in #200. This is not a production QuickBooks or bank write integration.

## Preconditions

- Inputs must be independently authorized, tenant/client/account scoped, normalized, and source-identifiable.
- Inputs use explicit account, unique durable source ID, posting date, signed Decimal amount, and optional transaction/reference ID.
- The matching engine never calls the provider, changes a workbook, posts a transaction, creates a financial obligation, or guesses classifications.
- A match requires unique candidate evidence: same account, same signed amount, date within the bounded configured tolerance and no conflicting explicit reference. Where multiple candidates or competing statement rows are plausible, it returns an ambiguous match.
- Statement-only and ledger-only entries are surfaced independently as exceptions.
- All decisions are deterministic and do not transform the source rows.

## Deferred gates

Production needs approved bank/credit-card structured imports, authorized QBO read model and an explicit statement-account to QBO-account mapping, source/ledger reconciliation against real accounting semantics, duplicate/transfer/one-to-many rules, sensitivity and retention policy, matching confidence/exception audit, and controlled workbook read/write verification. Bank-side changes, payments, invoices, credits and financial obligations remain outside autonomous authority.

## Validation

Run:

PYTHONPATH=implementation python -m pytest -q implementation/orchestrator/tests/test_accounting_reconciliation.py

## Relationship to QuickBooks sandbox

On October 12, 2026, Jason's live governed read capabilities successfully queried the AOT QBO sandbox company, chart of accounts, invoices, and bills. Those are connectivity and read-path proofs, **not** bank-statement reconciliation acceptance. This module's tests use synthetic financial records only.
