# Atomic Plumbing & Drain Cleaning — Client Security/Posture Acceptance

**Date:** 2026-09-25  
**Autotask company:** 333  
**DRMM site:** `a6af04fc-2e2a-4236-82ca-9d47ac616524`  
**DNSFilter organization:** `1110483`  
**Endpoint Backup customer:** `08dd6091-d9a8-499f-89aa-f9579896952f`

## Acceptance result

The first full OPS-005 mapped-client production review completed with the deterministic fail-closed evaluator and normalized durable report format.

- `confirmed_good`: 0
- `confirmed_gap`: 2
- `unknown`: 5
- `not_applicable`: 0
- `evidence_unavailable`: 5

No control is marked healthy from partial evidence. No remediation is authorized by the review.

## Confirmed gaps

1. **Managed antivirus protection** — `APD-50213` reports Windows Defender Antivirus `NotRunning`; `APD-HYPERV` reports Datto AV `RunningAndNotUpToDate`.
2. **Supported endpoint operating system** — Atomic still contains Windows 10 22H2 systems and an old Hyper-V Server 2012 host that are outside normal Microsoft support. Windows Server 2016 remains supported through its extended-support window and is not the basis of this gap.

## Unknown controls

BitLocker, managed EDR, DNSFilter complete-client coverage, managed backup complete-device coverage, and backup recency remain `unknown` because current evidence is partial or the AOT recency/coverage denominator is not yet formally established.

DNSFilter currently reports 23 protected agents, zero unprotected, and zero bypassed. That demonstrates active protection but does not prove every expected Atomic endpoint is represented; duplicate/stale-agent helper reads are also currently authorization-denied.

Endpoint Backup is bound to the exact Atomic customer and returns managed backup assets. `APD-50213` is currently online in DRMM while its returned backup asset last shows a successful backup on 2026-09-10, but the posture evaluator intentionally does not convert this into a gap until AOT's explicit backup-recency threshold is encoded.

## Evidence unavailable

DRMM monitoring health, VulScan coverage, Microsoft MFA, Conditional Access, and documentation completeness remain `evidence_unavailable` for this acceptance:

- account-level DRMM alert search still returns cross-site results even when a site selector is supplied, so it is excluded;
- no dedicated VulScan client-scoped capability/binding surfaced;
- Microsoft security reads are active, but no exact Atomic tenant binding is yet proven;
- IT Glue organization search remains correctly blocked by the information-release gate pending separate approval.

## Safety result

PASS. Cross-client evidence was not substituted, incomplete evidence did not become healthy, and the review generated proposals only. `automatic_changes_allowed=false` and `authority_semantics=evidence_only_never_grants_execution_authority` remain explicit in the durable report.
