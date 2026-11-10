# Project Jason Governance Simplification - Deployable Release-Control Contract

**Priority:** P0 / Owner-directed simplification
**Date:** 2026-11-10
**Scope:** release authorization and production promotion only. No provider capability expansion, ticket-processing behavior change, client communication change, or production deployment is authorized by this document.

## Objective

Return Project Jason to the operating principle:

> One Owner decision authorizes one genuinely risky outcome. Jason owns the engineering, testing, serialization, retries, verification, and rollback beneath that decision.

The release path must not require a second Owner decision merely to allow the already-approved exact release transaction to execute.

## Authoritative normal release contract

A normal release is:

1. **Build** one immutable candidate from protected source.
2. **Validate** targeted/foundational regression, production-equivalent preproduction, current production health, artifact identity, and rollback readiness.
3. **Approve once** using the exact Owner release request bound to candidate SHA, reviewed scope SHA-256, rollback SHA, manifest fingerprint, authenticated identity, and expiry/replay protection.
4. **Deploy once** under the exclusive Production Manager transaction lock. Technical worker quiescence remains mandatory while the mutation transaction is active.
5. **Verify** live runtime/MCP/host identity, functional health, ticket-processing continuity, protected drift, and the production manifest. Roll back automatically on failed acceptance.

## Controls retained

These remain mandatory:

- protected-source / exact-candidate identity;
- exact scope, rollback, and manifest binding in the Owner approval record;
- authenticated, replay-resistant Owner decision;
- production-equivalent preproduction and rollback readiness;
- exclusive production transaction locking;
- technical worker quiescence during mutation;
- production circuit breaker for genuine unhealthy state;
- current-scope and current-protected-source revalidation immediately before mutation;
- immutable/auditable evidence;
- post-deployment authoritative readback and rollback;
- tenant/client isolation and existing provider authorization boundaries;
- separate approval for disruptive endpoint actions such as reboot, shutdown, forced logoff, or network interruption.

## Complexity removed for new normal releases

The following are no longer independent Owner decisions or normal release admission requirements:

- a second explicit Owner unfreeze instruction;
- a second initial-unfreeze authorization receipt;
- replacement-unfreeze approval cards after a pre-mutation retry;
- initial-unfreeze renewal cards after the original release approval;
- a separate CCC human material-review approval;
- CCC-only follow-up cards after an exact release has already been approved.

The legacy production-freeze marker may remain temporarily as a compatibility/safety mechanism. The serialized Production Manager transaction can open and restore it using the exact Owner release transaction binding; the marker does not create a second human authorization requirement.

## Compatibility boundary

Legacy receipt readers, recovery paths, and old in-flight approval evidence remain readable during migration so existing audit history and recoverability are not destroyed. They are compatibility paths, not the normal workflow, and new releases must not mint new duplicate unfreeze authority.

The old technical worker-quiescence check is retained. This is a concurrency control, not an Owner authorization gate.

## Teams approval relationship

Teams routing/identity repair is a separate workstream. Its final implementation must preserve this simplified release contract:

- Teams delivery destination is not itself release authority.
- The authenticated approval mechanism supplies one exact Owner release decision.
- That decision must carry the exact release transaction binding.
- No V5/V4 routing implementation may reintroduce separate CCC or unfreeze Owner decisions.

## Ticket-processing non-interference

This change does not alter:

- autonomous ticket discovery/admission;
- Jason queue lifecycle;
- playbook matching or durable playbook authority;
- Datto/Autotask provider capabilities;
- active-work slot limits;
- ticket mutation/readback rules;
- endpoint safety boundaries;
- customer communication policy.

Release-manager technical quiescence remains in place specifically to prevent a deployment from racing active engineering/source mutation.

## Follow-on retirement after production acceptance

After this contract is production-verified:

1. retire issuance of obsolete CCC-only/unfreeze/replacement/renewal approval offers;
2. remove dead compatibility code only after no retained in-flight record depends on it;
3. convert standing Owner pause/freeze terminology to technical state controls where still required;

### Source implementation checkpoint — standing engineering pause

The standing Engineering Owner Pause is no longer part of the target replacement-lane authorization model. Replacement engineering lanes must instead prove the legacy monolithic engineering service is inactive and its timer is inactive plus disabled or masked before each run. The existing production-transaction lock and support-first lane serialization remain mandatory. The pause receipt/drop-in may remain in the currently installed production environment until this exact change is released; source readiness does not itself authorize removing installed controls.
4. keep only one normal release path and one bounded recovery path;
5. move independent security review to a risk-based rule (authorization/crypto/root/tenant/credential changes), not every routine release;
6. replace exact-version autonomous playbook promotion with authority-envelope promotion only after separate non-interference validation.

## Acceptance

The simplification is production-ready only when all of the following are true:

- exact Owner approval alone authorizes one serialized release transaction;
- changed candidate/scope/rollback/manifest fails closed;
- forged, stale, replayed, or mismatched approval fails closed;
- concurrent production mutation is impossible;
- legacy freeze is restored byte-identically on success/failure while retained;
- failed acceptance triggers rollback;
- no CCC-only or second-unfreeze Owner prompt is generated for a new normal release;
- autonomous ticket-processing regression remains green;
- Teams V5 reconciliation preserves the one-decision contract.

## Active integration coordination

Integration coordination: #2398 #2395 #2378 #2393 #2382 #2377 #2373 #2279

Later integration of these active overlapping branches must preserve the one-Owner-decision transaction contract. In particular, Teams identity/routing work may change who receives or authenticates the exact Owner decision, but it must not restore duplicate CCC, unfreeze, replacement-unfreeze, or renewal approvals. Orthogonal Workboard, client-notification, reachability, and superseded-approval recovery behavior must be rebased and regression-tested rather than discarded.
