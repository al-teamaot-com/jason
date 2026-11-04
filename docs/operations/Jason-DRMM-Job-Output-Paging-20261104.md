# Jason governed Datto RMM job-output pagination — preproduction candidate

**State:** Source-only; disabled by default; not merged, deployed, or accepted.
**Owner:** Project Jason / AOT.
**Authority:** Project Jason Governance Handbook (PMV3 release authorization), JES-001–004, J-002, J-405 and J-406.
**Scope:** Existing automation.job.output.read presentation only, behind the governed Central Orchestrator read boundary.

## Problem observed

On 2026-11-04, six owner-authorized diagnostic jobs ran on AL and AL-SAMSUNG, and all reached completed. The Windows and Network/DNS scripts produced valid summaries; however the generic MCP display returns the first 2,000 text characters plus a bounded suffix, making a full JSON read unavailable. Disk scripts exceeded the connector's separate 65,536-character source-output cap. These are distinct limits. No second component run may be issued simply because a read was incomplete.

## Additive output contract

When explicitly enabled and requested, the same authorized output read supports optional presentation-only arguments:

- output_offset: exact integer from 0 through 65536, inclusive.
- output_chars: exact integer from 1 through 1800, default 1600.

The output includes window offset, requested_chars, returned_chars, available_chars, has_more and provider_output_truncated. Each page retains the exact job, device, component and stdout/stderr stream binding. The page text is at most 1800 characters across all returned records. Clients may reconstruct the connector-buffered output using consecutive read-only page requests. If upstream Datto output was truncated, no reconstruction is claimed complete.

These arguments are never forwarded to the Datto provider; the provider receives only exact job/device/component/stream selectors. Unknown or mismatched output selector identities refuse to disclose content. Existing unpaged calls behave as before.

## Security and feature control

- New feature gate: JASON_DATTO_JOB_OUTPUT_PAGING_ENABLED defaults to false.
- Invalid inputs or disabled feature reject BEFORE any provider read.
- Aggregate information release expands for authorized readers even though each page is shorter than the former 2000-character display bound. **Classify as high risk** until security acceptance approves the information-release contract and secret-handling policy.
- Existing authentication, exact observe grants, Central Orchestrator, client/tenant boundary, provider bound and audit remain mandatory; never bypass this read surface through direct provider APIs or remote shell.
- No production flag, permissions, service, endpoint, job, component, policy or site variables are changed by the source PR.

## Tests and acceptance plan

1. Synthetic deterministic tests: reconstruct long output; truthful provider truncation metadata; wrong selector/stream fails closed; pagination disabled and invalid requests produce zero provider calls; paging arguments never reach the provider.
2. Reconcile current main and overlapping MCP/PMV3.1 PRs; verify protected CI and security tests.
3. Preproduction prove feature-off regression and an authorized feature-on read for an existing terminal job. Check sensitivity/redaction, identity/tenant isolation, and audit evidence. Never redispatch a component because output retrieval is incomplete.
4. Obtain exact-SHA Owner production approval with complete scope and verified LKG rollback, preserve production freeze, then deploy only via PMV3.1 and verify production health.
5. Roll back by disabling the flag through governed configuration or restoring last-known-good release. Feature-off restores prior output behavior.

## Documentation impact

Capability read-output contract: additive guarded display pagination; operations: this guide; architecture: no change to governance boundary; System Registry: no operational state change until approved activation; validation evidence must be attached to the PR.
