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
