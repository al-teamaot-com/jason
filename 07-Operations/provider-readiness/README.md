# Provider Readiness Operations

This directory contains standalone operational readiness runners.

These runners are intentionally separate from the live Jason conversation path.

## Current provider

OpenAI Hosted Conversation Kernel

## Current monitored capability

`conversation.intent.interpret`

## State database

Default:

`/var/lib/jason/openclaw/provider-readiness.sqlite3`

## Alert behavior

The runner persists readiness state and creates alert events only when the state materially changes.

Examples:

- first healthy -> unavailable transition: alert event created;
- repeated unavailable observation with same reason: no duplicate alert event;
- unavailable -> healthy: recovery alert event created.

Alert delivery is not yet enabled.

## Intended scheduling

Initial recommendation:

Run every 5 minutes.

The probe is bounded and should remain low-cost.

Scheduling and alert delivery should be activated only after the runner and state persistence are proven in isolation.

## Architectural constraint

Provider-specific probing remains inside provider/connector boundaries.

The readiness runner and state engine remain provider-neutral.

The monitoring path must not become a second execution authority and must not alter the live Teams request path.
