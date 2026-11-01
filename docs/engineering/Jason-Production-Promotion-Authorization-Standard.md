# J-CHANGE-003 — Production Promotion Authorization Standard

**Version:** 1.0
**Status:** Proposed under #758; non-production implementation only until separately approved
**Owner:** Jason Architecture Authority / Owner
**Authority:** Jason Constitution; J-CHANGE-001; Jason Deployment System
**Scope:** Promotion of Jason software, configuration, policy, playbooks, infrastructure, schema/state migrations, and deployment topology into the Production environment
**Canonical source:** Yes upon approval and merge
**Last reviewed:** 2026-10-02

## Purpose

This standard establishes one unambiguous authority boundary for Jason production deployment.

The controlling principles are:

> Deployable does not mean production-approved.

> No material Production promotion begins without explicit Owner approval bound to the exact promotion plan.

Development and Candidate/Staging automation may prepare, validate, package, test, and declare a release ready. Those states never grant Production authority.

## 1. Environment states

Jason SHALL distinguish at least:

### Development

Engineering iteration and validation. No Production authority.

### Candidate / Staging

An immutable candidate is exercised as it would be promoted. Candidate readiness may be determined automatically. No Production authority.

### Production

The live environment. Mutation is permitted only through the governed Production promotion path defined by this standard.

## 2. Standard promotion sequence

The normal sequence is:

Development
→ protected integration
→ immutable candidate artifact
→ non-production validation
→ READY FOR PRODUCTION
→ explicit Owner approval of the exact promotion plan
→ governed Production apply
→ verification / JAT
→ acceptance or governed rollback

No earlier state implies the later approval.

## 3. Immutable candidate requirement

Production SHALL be promoted only from immutable, already-built candidate material.

The plan SHALL identify, as applicable:

- Jason release/version;
- protected source SHA;
- artifact/image identity and cryptographic digest;
- configuration revision;
- MSP policy revision;
- playbook/bundle revision;
- schema/migration set;
- deployment-plan revision.

Moving branch names, mutable image tags without resolved immutable digests, unmerged feature branches, and ad-hoc host builds are not sufficient Production identities.

## 4. Production promotion plan

Before approval, JDS SHALL produce a human-readable and machine-readable plan.

The machine-readable plan SHALL include at minimum:

- unique promotion ID;
- target environment = Production;
- current deployment identity;
- target deployment identity;
- affected components;
- configuration/policy changes;
- migration/state changes;
- expected disruption/downtime;
- preflight evidence references;
- validation/JAT plan;
- rollback target and method;
- unresolved warnings/blockers;
- plan schema version.

The plan SHALL have a deterministic canonical SHA-256 fingerprint.

Any material plan change creates a new fingerprint and requires a new Owner approval.

## 5. Explicit Owner approval

Production approval SHALL be a durable governed record issued by an authorized Owner principal.

The approval SHALL bind:

- approval record ID;
- Owner principal identity;
- exact promotion ID;
- exact promotion-plan fingerprint;
- Production target;
- decision;
- approval timestamp;
- expiration;
- single-use/replay state.

A GitHub comment, PR approval, merge, passing CI check, issue closure, staging success, READY status, or conversational statement not captured by the governed approval mechanism SHALL NOT independently satisfy this runtime gate.

## 6. Technical enforcement

The Production apply capability SHALL fail closed unless the Central Orchestrator / deployment authority can verify a current, unconsumed Owner approval for the exact plan fingerprint.

The apply runner SHALL NOT accept a caller-supplied boolean such as approved=true as authority.

The approval record must come from the governed authority store or equivalent trusted approval adapter.

Immediately before material mutation, the runner SHALL:

1. recompute the plan fingerprint;
2. re-read the trusted approval;
3. confirm Owner authority;
4. confirm Production target;
5. confirm exact promotion ID and plan fingerprint;
6. confirm the approval is unexpired and unconsumed;
7. atomically reserve/consume the approval for that promotion attempt;
8. refuse execution if any check fails.

Re-use of a consumed approval is prohibited.

## 7. Preflight

Preflight is read-only unless a separately approved repair capability is invoked.

Before requesting Owner approval, preflight SHALL determine at minimum:

- current Production deployment identity;
- candidate integrity and authenticity;
- configuration/policy compatibility;
- required secrets/certificates presence without exposing values;
- storage/capacity/network/runtime readiness;
- required backups/checkpoints;
- migration and rollback viability;
- unresolved blockers;
- expected service impact.

Preflight success does not authorize Production mutation.

## 8. Migration and state safety

If the plan changes durable state or schema, it SHALL identify:

- each migration;
- source and target schema/state versions;
- whether startup performs an implicit migration;
- backup/checkpoint requirements;
- forward compatibility;
- rollback/downgrade compatibility;
- irreversible steps.

An irreversible migration requires explicit disclosure in the plan before Owner approval.

If rollback of application code would leave incompatible state, the plan SHALL NOT claim rollback is safe without a compatible state restore method.

## 9. Rollback readiness

Before material Production mutation:

- prior known-good immutable artifact identity must be recorded;
- rollback configuration/policy identity must be known;
- required state backup/checkpoint must exist;
- rollback procedure must match the planned migration/state transition;
- rollback verification must be defined.

If safe rollback cannot be established, that fact is an approval-time blocker or explicitly accepted risk; it must never be hidden.

## 10. Production apply boundary

Normal Production promotion SHALL NOT depend on:

- editing files directly on the Production host;
- editing a running container;
- copying source from an engineer/operator home directory;
- applying undocumented systemd changes;
- ad-hoc database commands;
- rebuilding from an arbitrary mutable checkout;
- bypassing Central Orchestration;
- bypassing the exact-plan approval binding.

The deployment runner may use privileged implementation mechanisms only through named, bounded, auditable deployment capabilities.

## 11. Verification and acceptance

Production success is not established by process/container startup alone.

Post-apply verification SHALL validate as applicable:

- exact artifact/image identity;
- source SHA;
- deployment manifest parity;
- configuration/policy revision;
- schema/state version;
- platform readiness;
- governance/authority health;
- secret-boundary health;
- provider/client isolation;
- required service/timer state;
- representative governed workflow behavior;
- JAT requirements.

Failure to verify the intended Production identity is a failed promotion.

## 12. Failure and rollback

On qualifying failure:

1. preserve failure evidence;
2. stop further promotion activity;
3. do not improvise a second unrelated Production fix;
4. invoke the approved rollback path when safe;
5. restore compatible state/configuration where required;
6. verify restored Production identity and health;
7. record final disposition;
8. escalate if rollback is unsafe or fails.

## 13. Evidence

Every Production promotion SHALL retain:

- promotion plan and fingerprint;
- immutable candidate identities/digests;
- approval record ID and Owner principal;
- approval timestamp and expiration;
- approval consumption record;
- pre-change deployment manifest;
- post-change deployment manifest;
- migration results;
- verification/JAT results;
- rollback evidence when applicable;
- final disposition.

## 14. Break-glass

Emergency/break-glass Production actions are outside the normal lane and require a separately defined, explicitly authorized, strongly audited procedure.

The existence of break-glass does not weaken or create an implicit bypass of the normal Production promotion gate.

## 15. Relationship to J-CHANGE-001

J-CHANGE-001 continues to govern source integration, immutable release selection, and serialization.

For Production execution, this standard is the controlling approval authority.

## 16. Relationship to J-CHANGE-002

J-CHANGE-002 may autonomously classify, prepare, test, package, and advance an eligible repair to READY FOR PRODUCTION.

J-CHANGE-002 does not waive the explicit Owner approval required by this standard for the final Production promotion.

Any prior statement that an Autonomous Repair Release can execute in Production without a new human/Owner approval is superseded by J-CHANGE-003 for Production execution.

## 17. Relationship to v1.0 deployability

Read-only deployability discovery may proceed independently.

Any deployability implementation that can create, migrate, upgrade, roll back, or promote a real Production environment SHALL consume this contract and SHALL NOT invent a parallel deployment authority model.

## 18. Acceptance tests

Before this control is activated in Production, non-production tests SHALL prove:

1. missing approval fails closed;
2. wrong Owner identity fails closed;
3. wrong target environment fails closed;
4. expired approval fails closed;
5. consumed/replayed approval fails closed;
6. plan mutation after approval fails closed;
7. artifact/source/config/policy/migration change alters the plan fingerprint;
8. exact approved plan can proceed to the bounded non-production apply seam;
9. verification failure follows the defined failure/rollback path;
10. no caller can bypass the gate with a boolean, environment variable, or alternate runner.

## 19. Activation rule

Merging this standard or its implementation does not itself authorize Production deployment.

Activation of the Production gate in the live environment requires a separate explicit Owner-approved Production promotion.
