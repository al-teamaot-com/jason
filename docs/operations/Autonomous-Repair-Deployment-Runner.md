# Autonomous Repair Deployment Runner

**Status:** Legacy repair preparation/status lane; Production apply disabled pending J-CHANGE-003 integration
**Owner:** Jason Architecture Authority
**Authority:** J-CHANGE-001; J-CHANGE-002; J-CHANGE-003; Jason Deployment System
**Scope:** Repair candidate validation and bounded handoff; no standing Production promotion authority
**Canonical source:** Yes
**Last reviewed:** 2026-10-02

## Purpose

The repair runner remains useful for deterministic repair-candidate validation and durable status evidence, but it is no longer an autonomous Production deployment authority.

J-CHANGE-002 may classify, validate, package, and prepare an eligible repair through READY FOR PRODUCTION. Final Production mutation is controlled by J-CHANGE-003 and requires explicit Owner approval bound to the exact Production promotion plan.

The legacy `deployment.repair.apply` capability therefore remains non-current/building. The repair profile may expose `deployment.repair.status` for read-only visibility, but it does not activate Production apply.

## Current flow

```text
merged SUPPORT repair PR
  -> deterministic J-CHANGE-002 validation
  -> prebuilt immutable candidate
  -> READY FOR PRODUCTION
  -> J-CHANGE-003 exact-plan Owner approval
  -> signed single-use Production promotion permit
  -> trusted jason.deployment.apply host runner
  -> verification / governed rollback
  -> durable evidence
```

## Authority boundary

`deployment.repair.apply` has no standing Production authority.

The former `jason-autonomy-worker` EXECUTE grant for repair deployment is removed. Only the read-only `deployment.repair.status` grant remains when the repair profile is enabled.

The apply capability is approval-required with Owner as the approver class and remains in BUILDING rather than ACTIVE until it is routed through the J-CHANGE-003 `jason.deployment.apply` lane.

A repair classification, merged PR, SUPPORT authorization, CI success, or prior approval of the repaired behavior does not authorize Production mutation.

Jason Runtime still receives no Docker socket, host shell, systemd control, or administrator authority.

## Candidate boundary

The host runner may independently revalidate the repair request, current live revision, merged PR, protected checks, and J-CHANGE-002 eligibility.

It requires an already-built immutable candidate image. The image source-revision label must exactly match the candidate SHA and the image must have an immutable SHA-256 image identity.

The runner does not build a candidate on the Production host.

The runner does not create a candidate Git worktree for deployment and does not execute deployment code from the candidate commit.

Candidate construction and candidate testing belong to the Candidate/Staging release process.

## Production handoff

The trusted installed runner invokes the canonical `infrastructure/jason-runtime/production-deploy.sh` path.

That path requires a signed Production promotion permit, the exact approved promotion-plan SHA-256, the exact candidate source SHA, the immutable candidate artifact digest, and an operation binding.

The generic live-container helper verifies and atomically consumes the permit before its first live Docker mutation.

A caller-supplied Boolean, environment flag, GitHub merge, or repair-classifier output cannot substitute for the signed permit.

## Verification and rollback

Success requires the live runtime to become healthy at the exact expected source revision.

If a post-deploy failure requires a standalone rollback, rollback requires a separately signed single-use rollback permit bound to the same approved plan and operation `rollback`.

A deploy permit cannot be replayed as a rollback permit. Missing, expired, mismatched, or consumed authority fails closed.

If rollback cannot be safely authorized or verified, Jason stops and escalates rather than improvising another Production mutation.

## Durable request/status boundary

The existing repair spool may retain bounded request and result evidence. Its presence is not Production authority.

`deployment.repair.status` may report exact bounded request/result state. It remains read-only.

## Production activation

There is no autonomous Production activation sequence under J-CHANGE-002.

The repair profile may activate read-only repair status. Production repair apply remains blocked until:

1. J-CHANGE-003 and its governed Owner approval authority are accepted;
2. the signed Production permit trust root and one-time claim store are installed through an approved Production promotion;
3. the trusted Production runner is installed and all supported release/configuration mutation paths are gated;
4. the #765 bypass, rollback, and failure acceptance suite passes in non-production;
5. the Owner separately approves activation in Production.

`automatic_production_execution_enabled` must remain `false`.

## Failure behavior

A failed or rejected repair produces bounded evidence and does not invent another Production action.

Repair preparation must fail closed rather than change candidate identity, widen scope, bypass protected checks, expose host authority, or silently convert itself into a Production deployment.

## Initial scope

The legacy repair preparation/status lane currently concerns the Jason runtime repair workflow only.

Teams gateway, MCP, OpenClaw, observability, provider systems, and other deployment components use the common J-CHANGE-003 Production promotion model rather than gaining separate autonomous deployment authority.
