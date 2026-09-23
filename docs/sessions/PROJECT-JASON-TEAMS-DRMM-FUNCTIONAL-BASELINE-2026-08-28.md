# Project Jason — Teams + Datto RMM Functional Baseline Checkpoint

**Date:** 2026-08-28  
**Branch:** `feature/jason-runtime-service`  
**Status:** Functional baseline substantially achieved; continue real-user testing before beginning gate-by-gate governance restoration.

## Objective

Establish a working-first Teams + Datto RMM conversational baseline before tightening governance and process controls.

The operating principle for this phase is:

> Get normal Teams + DRMM use working broadly and naturally first. Then reintroduce governance/security gates one at a time, proving after each gate that ordinary use remains intact.

## Functional baseline now demonstrated

The active Teams path can:

- authenticate and bind the Teams user through the existing Jason ingress/runtime path;
- use authorized read-only Datto RMM capabilities through the Central Orchestrator;
- resolve an endpoint independently of the requested fact and retain the resolved target across follow-up turns;
- answer ordinary endpoint questions from governed provider evidence without per-question fact mappings;
- use current endpoint state as baseline evidence and supplement it with specialized audit/software/alert reads when useful;
- keep historical alert evidence from displacing current resource/inventory evidence for current-state questions;
- interpret temporal scope generically (`current`, `historical`, `mixed`) so historical questions may use historical evidence without relying on phrase-specific routing;
- preserve conversation context for follow-ups such as pronouns referring to the previously resolved endpoint;
- interpret a conversational subject generically as an endpoint or a user without hard-coded wording;
- use the published `user_identity` selector on `endpoint.device.search` for user-to-endpoint relationship queries;
- preserve zero/one/many endpoint matches rather than forcing every query into exactly one endpoint;
- retain a user subject across clarification/follow-up turns rather than requiring the user to repeat the identity;
- state an evidence limitation when Datto RMM proves current/last-user association but not a true historical sign-in timeline.

## Representative proof

Endpoint conversation regression succeeded for:

- total RAM;
- reboot requirement;
- BIOS version;
- current free disk space;
- operating system;
- LAN/WAN IP addresses;
- CPU;
- motherboard/baseboard information;
- graphics adapter;
- network adapters;
- installed software;
- antivirus status;
- current alerts;
- resolved alert history;
- broad endpoint security/health summary.

A broad 18-question read-only Datto RMM battery returned no execution errors after the working-first baseline changes.

User-subject proof also succeeded: a user identity could resolve to multiple managed endpoints through the provider-neutral `user_identity` selector, and a follow-up about recent activity retained the same user subject while accurately explaining that the available evidence did not establish a historical interactive sign-in timeline.

## Architectural rules confirmed during this work

1. **No user-facing phrase, synonym, wording pattern, or example sentence may determine routing or behavior in deterministic code.**
2. Semantic interpretation belongs to the model; deterministic code carries structured meaning, validates capability authority, and executes supported provider operations.
3. Provider capability contracts and selector metadata are the execution vocabulary. Human wording is not.
4. Target identity is resolved independently from the fact being requested.
5. One-resource queries must not silently select the first of many results.
6. Multi-resource relationship queries may legitimately return a set.
7. Current direct resource/inventory evidence takes precedence over historical event evidence for current-state claims.
8. Historical evidence is available for genuinely historical questions based on semantic temporal scope, not phrase matching.
9. Evidence Before Assertion remains mandatory for operational claims.
10. Scripts, bespoke workflow branches, and per-fact/per-question mappings remain exceptions rather than the default architecture.

## Current runtime checkpoint

At the time of this checkpoint, the live Teams runtime had been promoted through the working-first sequence through the V6 permissive baseline, with the immediately prior V5 image/container preserved for rollback.

The V6 proof demonstrated:

- phrase hard-coding audit: PASS;
- resource/device hard-coding audit: PASS;
- focused tests: PASS;
- endpoint conversation regression: PASS;
- generic user-subject conversation proof: PASS;
- Teams gateway verification after promotion: PASS.

## Known limitation / continuing test area

Datto RMM `user_identity` relationship discovery is based on provider-reported endpoint user evidence such as last/current logged-in user. It does **not** by itself establish a historical interactive sign-in timeline.

Jason should preserve the user subject and explain this limitation rather than inventing historical activity or asking the user to repeat the subject. If a future authorized provider exposes genuine sign-in history, the model should be able to select that capability from its published contract without adding phrase-specific conversation logic.

## Next phase — after user confirms real Teams testing is satisfactory

Freeze the working behavior and restore governance/security controls incrementally in this order:

1. authenticated Teams ingress;
2. identity and organization authorization;
3. capability authorization;
4. resource/target authorization and identity invariance;
5. action-risk and approval controls for consequential mutations;
6. Evidence Before Assertion;
7. deterministic execution/evidence validation where needed;
8. outbound response safety, correlation, and audit controls.

After **each** restored gate, rerun the full Teams + Datto RMM acceptance battery plus unseen natural-language questions. If a gate breaks ordinary reasoning, fix the gate rather than teaching Jason another question.

## Acceptance standard for moving beyond the baseline

A Teams user should be able to ask essentially any reasonable authorized question about a Datto RMM endpoint or supported Datto relationship in natural language, and Jason should:

- understand the intended subject/relationship without phrase-specific code;
- choose among published authorized capabilities;
- remain bound to the correct resource(s);
- obtain and reason over governed provider evidence;
- return a useful grounded answer or a truthful evidence limitation;
- preserve conversational context across follow-up turns.

Only after this remains stable under real Teams use should the project move from working-first baseline mode into gate-by-gate governance restoration.
