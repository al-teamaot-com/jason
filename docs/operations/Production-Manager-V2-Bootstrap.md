# Production Manager V2 — Bootstrap

PM V2 is a parallel, isolated implementation governed by the approved
PM V2 Goal, Scope, and Definition of Success Agreement. The agreement is
canonical: functionality outside that scope requires explicit Owner agreement.

## Bootstrap responsibilities

The bootstrap provides:

- one durable SQLite work-state store;
- roadmap intake that distinguishes Owner-approved autonomous TODO work from
  proposal-only ideas;
- atomic worker leases and restart recovery;
- idempotency records for retryable/external actions;
- configuration-driven worker definitions and concurrency;
- parallel dispatch across independent work;
- component health/self-test state;
- read-only operator status commands;
- mandatory Microsoft Teams approval-channel configuration.

It does not create new production authority. Existing workers, approval
services, Release Manager, provider boundaries, and exact-release authority
remain authoritative and are reused rather than replaced.

## State progression

Proposal-only items are non-executable.

Authorized work starts as queued, becomes running under one bounded lease, and
moves to validation_ready after a reusable engineering worker succeeds. Worker
success is deliberately not completion. Functional, security, compliance,
documentation and release/production verification remain required before an
assignment can become complete.

Expired worker leases become retry_ready and can be safely reclaimed.

## Portability

Host paths and worker commands are configuration. Core PM V2 state uses SQLite
WAL storage and does not rely on a chat session or one worker process. The same
modules can run on another authorized host when configuration, state and
dependencies are made available.

## Approval

Normal approval is Microsoft Teams only. Terminal commands may repair genuine
technical problems but do not constitute approval.

## Parallel ownership and distributed execution

During V1/V2 coexistence, PM V2 observes the complete approved TODO/ideas
source but dispatches only TODO IDs explicitly assigned in versioned PM V2
configuration and only after an existing governed development issue identity is
known. The shared owner-approved development worker supports an exact issue
selector; its legacy global mode skips issues explicitly marked
Development controller: PM-V2.

Remote/distributed worker execution must reuse Jason's existing approved
role-based worker/provisioning architecture when that capability is available.
PM V2 does not create a competing remote shell or worker authority. Until a
remote worker role is independently accepted, PM V2 components remain portable
and can be relocated as services, while local worker execution is used only on
the host that owns the configured component.

## Production desired-state boundary

Persistent PM V2 execution is release-owned infrastructure. Do not install or
enable `jason-pm-v2-shadow.service` manually, from chat, or from an unreviewed
host bootstrap. The service may exist only after the exact candidate desired
state declares it and the existing root-governed host reconciliation stages the
reviewed policy delta, installs the source-controlled unit, aligns managed
engineering source, and activates it inside the release transaction.

The PM V2 shadow service remains **allowed, not required** while V1 is the
production authority. A rollback to a release that does not declare the service
must remove it through the existing managed-unit delta mechanism.

PM V2 health includes the fresh protected production-drift readback. A locally
healthy database/process is not sufficient: stale, unavailable, or non-PASS
production drift evidence makes PM V2 health degraded. This rule was added after
acceptance testing caught an out-of-band PM V2 user service opening the protected
production circuit breaker even though its local self-test was green.

## Existing Teams release lane: protected-core activation

Per explicit Owner agreement on 2026-10-31, PM V2 reuses the existing Teams
release approval system for `production_control_core`; it does not create a
second approval engine. The reviewed activation is source-bound, rollback-safe,
and fail-closed as described in
`Teams-Protected-Release-Approval-Gates-2026-10-18.md`.

The approval policy and running mode must move together inside the governed
Release Manager transaction. Preproduction keeps the lane off. A successful
runtime transition must prove the exact policy digest and `owner_reviewed`
mode; rollback must restore the prior policy and mode. Approval never lifts the
separate production deployment freeze and never expands provider or endpoint
authority.

## Root migration bootstrap sequencing — 2026-10-31

Production acceptance exposed a protected-root bootstrap loop: the currently
installed root host worker verifies any new desired-state unit with its
currently trusted migration helper **before** candidate staging can replace
that helper. Therefore the first release that both teaches the helper a new PM
V2 unit plan and declares that unit cannot pass the old helper's preflight.

The governed sequence is now two releases:

1. **Bootstrap release:** deploy the reviewed owner-reviewed Teams lane and the
   updated trusted root helper/worker, but do **not** declare or install
   `jason-pm-v2-shadow.service` yet.
2. **PM V2 shadow release:** after the new root helper is live, add exactly the
   previously reviewed optional PM V2 shadow unit to desired state. That second
   release must use the normal exact-SHA Teams approval lane and all existing
   CCC, scope, rollback, drift, and freeze controls.

This is sequencing only. It does not remove the PM V2 persistence requirement
and it does not weaken root desired-state validation.

Rollback authority ordering is also explicit: if an owner-reviewed candidate
fails after staging policy V2, restore the prior V1 approval policy **before**
starting the baseline `owner_only_pilot` runtime. After baseline health is
verified, confirm runtime mode and restored policy agree. Never boot V1 against
V2 policy during rollback.

## One-time Owner material-review waiver — 2026-10-31

The AOT Owner may explicitly make a **one-release constitutional exception** to
the separate CCC human material-review artifact when a bootstrap dependency
would otherwise make the first protected-core activation circular. This is not
a waiver of CCC technical certification and is not standing authority.

The exception is valid only when all of the following are true:

- the release is `production_control_core` and already `production_eligible`;
- the Owner approval is exact-SHA bound to the same candidate;
- the complete manual scope review is current and the waiver is bound to its
  exact `scope_sha256`;
- the waiver records `person-al`, `explicit_owner_instruction`, a rationale,
  `one_time=true`, and the exact candidate SHA;
- the independent CCC checker still runs normally. The only non-PASS check the
  waiver may satisfy is the canonical
  `material-change-owner-review=NOT_PROVEN` caused by absence of the separate
  human review artifact;
- before deployment, the normal live-runtime alignment gap may coexist with
  that one waived human-review check. No checker-currentness, security,
  provider, host, monitoring, constitutional, release-validation or other CCC
  failure is waived;
- after deployment, every technical CCC check and runtime/source alignment must
  pass. The release record must state that the raw CCC report remained
  `NOT_PROVEN` only because the human review was Owner-waived; it must never be
  relabeled as an ordinary CCC PASS;
- rollback, drift, scope, exact-source, production-freeze and transaction-lock
  requirements remain unchanged.

A rolled-back, reissued, superseded or different release receives no waiver by
inheritance. A new SHA or scope digest requires a new explicit Owner decision.
Once the normal V2 Teams owner-review path is live, routine releases should use
that path rather than this bootstrap exception.
