# Coordinated scoped release extension — source review

**Status:** Source-review candidate; not a native installation authorization,
production eligibility record, or production deployment.

## Objective and scope

Extend the existing scoped release architecture to reason about exact
component images and independently reviewed source projections, while retaining
the original host revision as a separate immutable rollback anchor. The initial
typed operation supports Runtime, MCP pilot, and Teams Gateway, in a fixed
dependency order. It permits no arbitrary container, shell, environment, mount,
provider write, standing permission, or change to the Ticket Core.

The first application is the already merged Teams shared workflow from PR
#2700. Only the reviewed immutable images and private manifest bound by
config/coordinated-scoped-release-review.json are eligible for subsequent
review. The full live manifest is kept in private engineering custody; it is
not published to this public repository. The root-owned review pin must match
the manifest digest. Source-only admission is not production admission.

## Controls

- Preserve original v1 M365 request and proof format, root trust, and policy.
- Use existing one-use signed Owner proof, shared approval-consumption ledger,
  legacy and PMv4 transaction locks, protected root breaker/drift evidence,
  and existing native container replacement helper.
- Retain exact original container IDs, image digests and source revisions.
  Preserve the exact active freeze in legacy schema 2 transactions. Schema 3
  instead binds the independently installed permanent-retirement policy and
  verifies that no active freeze marker exists. Never cross-accept proofs or
  allow a scoped transaction to retire or recreate the global marker. Reverse rollback on failure; no automatic
  re-promotion and no automatic breaker closure.
- Separate root-owned component readback from the original host LKG. Require
  actual image, revision and container identity; reject unknown mixed states.
- Preserve Ticket Core and OpenBao. The specifically attested isolated OOM-stopped
  shadow remains outside production health; it must not be restarted or altered.
- Enforce rollback capacity and never delete unrelated retained originals.
- A component scope cannot authorize a provider mutation, Teams policy
  activation, privileged root installation, or any future release.

## Verification performed in engineering

The exact three candidate images passed isolated builds/smoke checks and
native-helper read-only preflight. A real disposable, network-disabled
three-image rollback rehearsal verified full and interrupted rollout recovery
with original disposable IDs restored and production peers unchanged. The
native host unit suite uses injected I/O and test-only signatures. It is
not a live root integration test. Production remains on the original images.

## Required native migration gate

This source change does not install anything. The current installed v1 control
plane cannot run this extension. An independently authorized migration must:

1. Bind the exact reviewed source commit, complete installed dependency hashes,
   root-owned private manifest/profile, a root-controlled Git cache, and the
   existing signed Owner trust. Validate all current production preconditions
   and retain a reversible before-image of every changed native artifact.
2. Install the versioned coordinator, native host, root dispatcher, readback
   module, existing native deploy helper under its versioned name, required
   helper dependency, and exact root-owned policy with immutable permissions.
   Keep the legacy v1 implementation and proof semantics intact.
3. Integrate the existing request/recovery scheduler with the exact new
   dispatcher. Verify effective unit commands and scheduled recovery, not
   merely unit presence. Preserve the existing v1 scheduler and update any
   affected root trust digests through its approved migration mechanism.
4. Migrate the effective native guard, self-heal and root transition readers
   through their current source-pinned installation mechanisms. Preserve
   existing source pins, health checks, root breaker semantics and authority.
   Verify the actual running reader inventory before issuing a migration
   receipt. Source tests do not substitute for this receipt.
5. Connect the already governed Owner-signing flow to the coordinated native
   eligibility record without weakening the existing independently verified
   identity, exact scope, expiry, one-use, or provider-write restrictions.
   The existing v1 local issuer does not issue v2 proofs unchanged.
6. Verify native stage against live immutable images, actual protected health,
   signed review, current rollback capacity, complete configuration and source
   provenance. Rehearse the installed root reader/dispatcher and recovery
   integration in isolated infrastructure. Obtain a separate exact signed
   Owner production decision before promotion.
7. After any permitted promotion, verify the entire component/readback chain,
   production peers, rollback retention, unchanged release-mode policy and actual Teams
   behavior. Policy activation requires its own approved scope.

No production installation, stage eligibility, or Owner approval is claimed
by this document. The installation transaction and issuer/scheduler migration
are separate remaining engineering work and must be reviewed before root
execution. The draft source extension is not itself approval to merge or
activate privileged code.

## Retirement-policy reconciliation

The reviewed integration with PR #2767 retains legacy schema 2 and adds
schema 3 exact normal-policy binding for the manifest, profile, stage
record, signed decision, native host gate and component readback. The
versioned successor denies an old proof, wrong policy, replay, a missing
retirement record or an unexpectedly present freeze. Existing tests
continue to exercise the historical signature and reverse-order rollback.

Verification: 159 scoped controller/host/readback/legacy tests and 89
shared native guard, self-heal, transition and drift tests passed in the
isolated engineering checkout. No production mode or state changed.
The exact private manifest remains legacy-mode until a root-authenticated
retirement transaction and native migration have been accepted. Do not
install the draft controller or mint a normal-mode eligibility receipt
from this source evidence.

## Existing Owner approval route

Normal-mode native stage now publishes a root-owned, read-only exact eligibility projection. The existing authenticated MCP approve_release_candidate path selects this typed route only for a matching release identity and independently read retirement-policy digest. It refuses ambiguous ordinary/coordinated records, untrusted or changed eligibility, legacy mode, mismatched identity, and repeat proof issuance. The native controller independently verifies the private offer and signature and consumes the one-use decision. No new capability, authority grant or provider-write right was introduced. The root installer, effective scheduler and reader migration remain required before this source path may operate live.
