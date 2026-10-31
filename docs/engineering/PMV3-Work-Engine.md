# PMV3 Work Engine

PMV3 is an isolated replacement candidate for the Production Manager work engine.
It does not inherit production authority from PMV2 and is not authorized to deploy
itself.

## Agreement-driven behavior

The engine is built around:

SCAN -> SELECT RUNNABLE -> EXECUTE -> VERIFY -> RETRY/RECOVER -> RECHECK -> CONTINUE

The implementation must prove the following before production integration:

- approved runnable work continues without repeated operator prompts;
- a blocked task does not block unrelated runnable work;
- transient failures receive bounded retry/backoff and authoritative re-evaluation;
- waiting work wakes when its dependency becomes true;
- interrupted work resumes after restart;
- durable action receipts prevent duplicate execution;
- external authority/credential/billing gates remain external and are not invented;
- completion percentage describes the entire accepted PMV3 workload, not setup steps.

## Isolation

The first PMV3 implementation is intentionally handler-driven. Tests and
preproduction adapters may inject actions. No production provider worker is wired
to this engine until the scheduler/recovery acceptance suite passes.


## Approval channel

Teams is the only human approval channel for PMV3.

Approval-required work is not runnable unless PMV3 receives a verified approval
decision from Jason's authenticated Teams Approval Service / Universal Teams
Approval path and the decision is bound to the exact approval request.

The following are never approval:
- SSH or shell commands;
- local files or environment variables;
- GitHub comments or repository access;
- typed chat text such as "approve";
- direct state/database edits;
- copied, expired, mismatched, replayed or unverified approval payloads.

Teams Deny leaves the work non-runnable. PMV3 must never instruct the Owner to
SSH to Jason to approve work.
