# Project Jason Operations Documentation

**Status:** Active operational documentation authority map  
**Owner:** Jason Architecture Authority  
**Higher authority:** Jason Constitution, approved project ADRs, canonical J-series architecture, governed component/capability specifications, identity/authority policy, and System Registry structured truth

## Purpose

This directory contains current and repeatable operational material used to deploy, verify, recover, validate, and safely operate Jason.

Operational documentation explains **how to perform or verify governed work**. It does not independently grant identity, approval, capability, provider, business, or execution authority, and it does not override higher-authority governance or architecture.

## What belongs here

### Repeatable procedures and runbooks

Runbooks, checklists, activation procedures, deployment/recovery procedures, and bounded validation procedures remain in `docs/operations/` when they are intended to be used again.

Examples include:

- `CAP-007-AWS-SES-Activation-Runbook.md`;
- `INF-001-Morning-Execution-Checklist.md`;
- `INF-010-Microsoft-Cloud-Deployment-Checklist.md`;
- `INF-015-AWS-Provider-Deployment-Checklist.md`;
- `IT-Glue-Datto-Resource-Convergence-Checklist.md`;
- `Jason-Bootstrap-and-Secrets-Runbook.md`;
- `OpenClaw-Ed25519-Key-Rotation.md`;
- `OpenClaw-JKD001-Operational-Hardening.md`;
- `OpenClaw-JKD001-Production-Packaging.md`;
- `Provider-Secret-Provisioning.md`;
- `Runbook-Teams-Integration.md`;
- `System-Registry-Production-Verification-Runbook.md`;
- `Teams-Approval-Deployment-and-Recovery.md`;
- `Teams-Integration-Security-Cleanup-Checklist.md`.

`Runbook-Teams-Integration.md` is the current operational owner for Microsoft Teams ingress deployment/verification/rollback. As of the 2026-08-15 production cutover, ordinary inbound Teams is owned by the direct `jason-teams-gateway` under ADR-009; OpenClaw remains a separate deployed component and may still support approved outbound/proactive Teams behavior. Do not infer current ingress ownership from older OpenClaw runbooks or internal provider startup logs.

`OPS-ITGLUE-DATTO-LIVE-CONVERGENCE-PROOF.md` also remains here despite its historical filename because its content defines a reusable, observe-only proof procedure with prerequisites, bounded discovery, positive/negative test cases, evidence handling, and success criteria. Its embedded historical result does not change the document's primary procedural role.

### Deployment and initialization records

Records such as:

- `Jason-OpenBao-Initialization-and-Recovery-Record.md`; and
- `Jason-Secret-Provider-Deployment-Record.md`

remain operational records when they define or preserve the governed deployment/bootstrap state needed for safe operation. They are not substitutes for current observed production state.

### Generated current-state representation

`System-Registry-Current-Operational-State.md` is a generated human-readable view derived from System Registry structured truth. It may be used for readability and review, but the System Registry remains authoritative for operational topology and lifecycle state.

After a governed production topology change, update the machine-readable System Registry/lifecycle evidence first and regenerate the human view with `python tools/system_registry_docs.py`. Do not hand-maintain a competing topology table in a runbook.

## What does not belong here

Point-in-time host proofs, live-pilot evidence, reconciliation evidence, and session-specific verification outcomes belong in `docs/sessions/` when their primary purpose is to preserve what was proven at a particular time.

For example, the direct Teams ingress cutover proof is preserved at:

`docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`

A dated proof record must not be retained in `docs/operations/` merely because it concerns an operational capability. Likewise, a reusable runbook must not be moved to `docs/sessions/` merely because its filename contains the word `proof`.

## Authority and current-state rules

Operational documentation is subordinate to Jason's governance hierarchy.

Before asserting current production state:

1. use the System Registry for declared/effective operational topology and lifecycle facts;
2. use current Git for source/revision facts;
3. obtain fresh host/runtime evidence when the fact requires physical verification;
4. treat historical proofs as evidence of what was true when proven, not as perpetual current-state claims.

For Teams specifically, current external ingress ownership must be verified from current System Registry plus actual host/container port ownership when operationally material. An OpenClaw log line such as `msteams starting provider (port 3978)` does not prove that OpenClaw owns the host's externally reachable port.

If an operational record contains a durable architecture, authority, security, or policy rule that is not represented in its governed owner, reconcile that rule into the appropriate canonical record rather than allowing the operations document to become hidden architecture authority.

## Evidence identity and migration

Moving a historical proof from `docs/operations/` to `docs/sessions/` is a documentation-classification change, not a change to what the proof established. Preserve its content, date, evidence identifiers, hashes, and material conclusions. Update only current repository-path references needed to keep the record discoverable and accurate.

Historical references that intentionally describe a former repository layout may remain as historical text. Current operator directions must use current governed paths.
