# Incident - Hosted Reasoning Unavailable Due to Provider Credit Exhaustion

Date: 2026-08-24

Status: Root cause established

## Summary

Jason Teams requests began returning:

> Jason could not safely process that request. No action was taken.

The failure initially appeared to be a Jason production-code or conversation-runtime problem.

Investigation ultimately established that Jason itself was healthy and that the failure occurred because the configured OpenAI API account had no remaining API credits.

## User-visible symptom

Normal conversational requests through Teams failed before reaching governed operational execution.

The security audit recorded:

- successful Teams authentication;
- conversation failure;
- `ConversationKernelError`;
- `all configured reasoning backends failed bounded validation`.

No Central Orchestrator execution occurred for the failed request.

## Verified healthy components

The investigation established that:

- `jason-runtime` was running and healthy;
- Teams ingress authentication succeeded;
- OpenAI DNS resolution succeeded;
- HTTPS connectivity to `api.openai.com` succeeded;
- OpenBao successfully resolved the configured OpenAI API credential;
- the OpenAI API key was valid;
- authenticated access to `GET /v1/models` returned HTTP 200.

## Root cause

A direct authenticated request to the OpenAI Responses API returned:

- HTTP status: `429`
- error type: `insufficient_quota`
- error code: `credit_balance_exhausted`
- provider message: no credits remained for API execution.

The hosted reasoning provider therefore could not perform:

- `conversation.intent.interpret`
- `conversation.evidence.assess`

Jason correctly failed closed, but the operational reason was not surfaced clearly enough to distinguish an external-provider availability condition from a Jason software defect.

## Root-cause classification

Category:

`external_provider_capacity`

Canonical reason:

`quota_exhausted`

Affected provider:

`provider.openai-conversation-kernel`

Affected capabilities:

- `conversation.intent.interpret`
- `conversation.evidence.assess`

Jason runtime state:

`HEALTHY`

Provider capability-readiness state:

`UNAVAILABLE`

## Corrective action

Restore API credit / billing capacity for the governed OpenAI provider account used by Jason.

## Preventive action

Implement constitutional provider and dependency capability-readiness monitoring.

The monitoring system must separately assess:

1. Jason/component runtime health.
2. External dependency reachability.
3. Authentication / credential readiness.
4. Actual governed capability execution readiness.

A process being healthy must not be treated as proof that the capabilities depending on it are operationally ready.

## Required alert behavior

When a provider transitions from healthy to unavailable, Jason operations should receive one actionable alert identifying:

- affected provider;
- affected capabilities;
- canonical failure reason;
- whether Jason itself remains healthy;
- first observed time;
- recommended operator action.

Repeated probes must not create duplicate alert noise while the provider remains in the same state.

Recovery should produce a corresponding recovery notification.

## Architectural lesson

External dependency failure must be classified before it is treated as a Jason production-code defect.

Jason must preserve the distinction among:

- component health;
- dependency reachability;
- authentication health;
- provider capability readiness;
- governed execution health.

This incident is the initial acceptance case for the Provider Capability Readiness workstream.
