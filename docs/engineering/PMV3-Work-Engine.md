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
