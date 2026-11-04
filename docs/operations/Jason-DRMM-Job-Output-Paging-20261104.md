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
- Even when the feature gate is enabled, JASON_DATTO_JOB_OUTPUT_PAGING_COMPONENT_UIDS must independently enroll each reviewed component by its exact existing Datto UID. Empty/mismatched enrollment rejects before any provider read.
- The provider output must begin with the AOT DIAGNOSTIC header and contain the AOT_DIAGNOSTIC_JSON_BEGIN marker. Unexpected/unreviewed output is rejected at the evidence projection boundary; no fallback to raw stdout.
- Paged stderr is also enrollment-gated, and provider output remains subject to existing authorized exact job/device/component/stream bindings.
- Invalid inputs, disabled feature or unenrolled component reject BEFORE any provider read.
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

## Security review addendum (2026-11-04)

Review found broad paged access to arbitrary automation jobs would be an avoidable disclosure expansion. The source was hardened before merging: default-disabled feature flag, separately configured exact component UID enrollment (empty by default), output envelope validation, canonical provider selector match, and fail-closed projection errors. Standard unpaged disclosure limits remain unchanged. No pagination setting has been enabled in production, and no arbitrary log-disclosure exception has been granted.

The dedicated CI workflow includes positive bounded reconstruction, upstream truncation honesty, invalid window inputs, no-provider-call feature-off / no-enrollment refusal, missing diagnostic envelope refusal, failure-mode handling, and existing governed-read failure-contract regression cases. Full separate authorization regressions remain in SEC-007 and other foundational workflows.

Remaining security boundary before any feature activation: prove that the enrolled component UID currently resolves to the reviewed approved script metadata, that returned diagnostic text does not contain operational secrets or other disallowed client content, and that preproduction grants/tenant isolation and audit are intact. Do not label that independent provider-backed validation complete based on mocked fixtures.

## Preproduction authentication and provider-fixture evidence

The independent preproduction harness tests exact MCP public read entrypoint through the normal observe-only identity/authority check and Central Orchestrator request construction, using a synthetic provider response with no Datto credentials and no live endpoint changes. Positive evidence reassembles a greater-than-10 KB AOT diagnostic JSON report from 1,600-character governed windows and validates the exact original JSON. Negative evidence denies the read when the simulated requester lacks observe authority and verifies the provider stub was never called. This is a **mocked preproduction acceptance** and does not substitute for live provider-backed validation once the exact reviewed source is eligible for activation.
