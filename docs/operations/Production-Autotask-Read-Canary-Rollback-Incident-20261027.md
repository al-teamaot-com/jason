# Autotask v11 production read failure and verified rollback — 2026-10-27

**Source-only root-cause and remediation record. Deployment freeze remains active.**

## Observed outcome

Owner-approved immutable revision `240debfd17e3fe387d73b58f4a5edab551cfb6b6`
passed native preproduction, production container health checks, postproduction CCC,
drift verification and release closeout. Immediately afterward, genuine
ChatGPT-to-Jason `service.ticket.count`, `service.ticket.search` and
`service.entity.search` returned information-release denials
(`SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED`). The original ticket-read
path had passed a controlled 72-ticket window before deployment.

The Owner's required external functional acceptance test therefore failed,
despite a release marked `closed`. The first two emergency rollback
attempts were blocked; an independently verified controlled alignment and
native host reconciliation were needed to complete recovery. All runtime,
MCP, immutable host, Release Manager and complete manifest identities were
restored to `8559cbb84aba2d9acb636ac57fbdab9f00dbda78`. Protected root
last-known-good, circuit breaker closed state and drift PASS were independently
read back. The same governed ticket-read query succeeded again after recovery.

## Deterministic rollback defects proven

1. Native rollback supplied the v10 profile as
   `JASON_PROVIDER_READ_ACTIVATION_PROFILE` while the reviewed v11
   deployment scripts correctly require that candidate override to match
   the v11 source. Both rollback scripts refused the invocation before
   making changes. The corrected native wrapper leaves candidate selection
   to the immutable script and supplies only the independently verified
   `JASON_PROVIDER_READ_ROLLBACK_PROFILE=v10`.
2. The root host reconciler rejected an approved historical rollback when
   the circuit breaker was open and the protected LKG was the newly
   promoted revision. Future release transitions now retain the previous
   *root-owned, complete, independently verified* last-known-good manifest;
   the root worker may use only that exact prior revision under an open
   breaker, subject to immutable migration-policy digest and Git ancestry
   checks. This cannot authorize arbitrary older releases.
3. Runtime rollback verification previously raced Docker's health probe.
   It now waits for the canonical runtime HEALTHY check before evaluating
   rollback identity.

## Still not proved

The transient or persistent cause of the **live requester authorization**
denials has **not** been conclusively identified. Unit and source-level
authorization tests do not replace a real authenticated MCP read.
No loosening of source/requester disclosure restrictions is authorized.

**P0 release acceptance requirement:** Future read-surface releases must
run actual authenticated connected MCP counts, multi-page searches,
exact-ID readback and representative new generic reads *after* promotion,
before the owner or automation can accept completion. If any fails,
rollback must be proven all the way through root reconciliation and
frozen production must remain frozen until external acceptance.

The code changes here repair rollback preconditions; **they do not
claim to implement that external acceptance protocol**. Its end-to-end
implementation and verification remains a separate release blocker.
