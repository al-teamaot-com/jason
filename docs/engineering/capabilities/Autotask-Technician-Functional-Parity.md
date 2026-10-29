# Autotask technician functional parity — engineering contract

## Standing requirement

Any action an authorized AOT technician can perform to, in, or for an Autotask ticket must be operable through Jason, subject to the same user/client scope, provider capability and approval requirements. This is a *standing product requirement*, not a sequence of one-off feature requests.

## Architecture

1. **Observe continuously:** acquire independently authenticated Autotask API documentation/metadata and technician UI feature inventories. Do not scrape arbitrary sites or infer execution rights from a feature name.
2. **Discover and diff:** compare those inventories against Jason's registered provider routes and governed capabilities, using `tools/autotask_technician_gap_report.py`. Detect new features and changes instead of assuming the existing integration covers them.
3. **Resolve the gap:** prefer the supported Autotask provider interface. If a UI-only feature has no supported API equivalent, evaluate a separately authenticated, auditable technician UI adapter. No hidden sessions, undocumented privileged API calls or blind clicking.
4. **Govern every execution:** requester identity and role, client scope, exact source/target objects, field semantics, appropriate billing/charge/time-entry handling, immutable audit, replay protection, policy decisions and approval binding precede any mutation.
5. **Validate:** prove positive and denied cases against the designated test tenant, read back provider state, check duplicate/retry behavior and unchanged baseline functionality.
6. **Promote through Production Manager:** preserve unrelated protected-main development, exact source SHA, CI results, preproduction acceptance and rollback. Production activation is separately authorized.

## Candidate workflow

A discovery finding is **never** an executable capability. It must advance through provider contract verification, security review, implementation/adapter selection, deterministic tests, provider-backed acceptance, promotion, and then requester-level authorization. New features can be *detected* without changing runtime code; no system can safely promise automatic execution of every future feature before semantics, provider support and permissions are known.

Ticket merging is an acceptance use case rather than a special-case script: verify retention of timeline, related notes, attachments, unposted/posted time and charges, billing associations, links, original/retained ticket identity, client and contact, notification semantics and rollback/conservation. Do not simulate a native merge by copying notes and closing a ticket unless explicitly approved as a documented equivalent.

## Initial implementation scope

This first PR creates an inert inventory-and-diff library, CLI, and regression tests. It does **not** yet wire authenticated provider/UI collectors, dynamic provider adapter construction or ticket merging. Those are required before claiming technician parity or production readiness. Production freeze remains in effect.
