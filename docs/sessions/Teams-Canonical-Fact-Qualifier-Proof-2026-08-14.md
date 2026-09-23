# Teams Canonical-Fact Qualifier Proof — 2026-08-14

**Classification:** Evidence / durable session proof
**Status:** Live-proven and durable implementation
**Implementation commit:** `2e5db00db970a5cec4e153e54abbd3600819c313` — `Resolve qualified canonical endpoint facts`
**Workstream:** Governed natural-language canonical-fact qualification

## Purpose

This record preserves the design, failed experiments, deterministic implementation, validation, deployment, and signed production proof for canonical-fact qualifier resolution.

The motivating request was:

`What IP is AOT-50282 using internally?`

Jason already had governed LAN and WAN facts and provider evidence. The defect was semantic interpretation collapsing qualifier-rich wording to generic `ip address`.

## Authority boundary

The implementation preserves these boundaries:

- Teams/OpenClaw remain interface and transport only.
- Central Orchestrator remains the execution/coordinating authority.
- Resource selectors remain separate from requested facts.
- Eligible facts come from governed provider-neutral capability metadata.
- Qualification does not select providers or provider fields.
- Operational values remain provider-derived.
- Ambiguity fails closed before orchestration.
- No question-specific Datto script or provider mapping was introduced.

## Failed model experiments

A bounded local Qwen model was evaluated using only human wording and allowlisted canonical facts.

The first experiment misclassified:

`internet-facing IP -> LAN IP address`

A revised experiment correctly handled qualified examples but guessed:

`What IP does AOT-50282 have? -> LAN IP address`

The bare request is ambiguous.

Prompt tuning was therefore rejected as the fail-closed production control. The deployed qualifier mechanism is deterministic.

## Deterministic implementation

The canonical-fact vocabulary exposes tri-state qualifier analysis:

- `not_applicable`;
- `resolved`;
- `ambiguous`.

A fact resolves only when a shared anchor is present and exactly one eligible candidate has discriminating recognition language.

A shared anchor with no unique discriminator is ambiguous.

Conflicting candidate discriminators are ambiguous.

For LAN/WAN:

- internal/private/local -> LAN;
- public/external/internet-facing -> WAN;
- bare IP -> ambiguous;
- internal + public IP -> ambiguous.

Qualifier analysis executes before ordinary explicit alias matching.

This ordering was established after an initial regression showed that `internal public IP` could otherwise be incorrectly captured by the longer `public IP` alias.

That failed implementation was automatically rolled back before the durable correction.

Ambiguous qualifier outcomes raise `ConversationIntentUnresolvedError` and stop before generic resource-language reasoning, action reasoning, capability planning, or orchestration.

## Test proof

Regression coverage established:

- internal IP -> LAN;
- private-network IP -> LAN;
- local-network IP -> LAN;
- external IP -> WAN;
- public IP -> WAN;
- internet-facing IP -> WAN;
- bare IP -> ambiguity;
- conflicting internal/public IP -> ambiguity;
- unrelated uses of `internal` do not activate the IP contrast;
- qualified routing still selects the normal provider-neutral endpoint capability;
- ambiguous requests do not reach language fallback.

Focused and complete target regression suites passed.

The combined pre-commit semantic revalidation suite passed.

## Deployment proof

Previous production image:

`sha256:060f0b5fe98611fc9bb634bc2d11d87d239b685fb441a4b6fae35103298e8ac6`

Verified rollback tag:

`jason-runtime:pre-canonical-qualifier-20260814T154359Z`

New production image:

`sha256:efb0ea07fb255a77e338319a09187bc69b1b72ee84fd4682a35bf508600625f8`

Runtime health passed.

Image parity passed.

Host/container source parity passed for canonical vocabulary, conversational resource interpretation, and runtime composition.

OpenClaw was not restarted.

Provider configuration was unchanged.

No provider write occurred.

Secret contents were not read or printed.

## Signed production ingress proof

### Internal request

`What IP is AOT-50282 using internally?`

Result:

- HTTP 200;
- completed;
- orchestration succeeded;
- canonical fact `LAN IP address`.

Audit:

- authenticated;
- completed.

### Internet-facing request

`What is the internet-facing IP for AOT-50282?`

Result:

- HTTP 200;
- completed;
- orchestration succeeded;
- canonical fact `WAN IP address`.

Audit:

- authenticated;
- completed.

### Ambiguous request

`What IP does AOT-50282 have?`

Result:

- HTTP 400;
- rejected;
- `conversation_unresolved`.

Audit:

- authenticated;
- rejected;
- no completion event.

Historical proof correlations:

- internal: `cb4148e2-705f-443e-ab2c-e54b6c60bc66`;
- external: `63eb0b39-b637-402a-9920-a79105d06702`;
- ambiguous: `2080bab8-5692-4365-bfa6-863bc5c7e8d8`.

## Durable implementation

Commit:

`2e5db00db970a5cec4e153e54abbd3600819c313`

Commit message:

`Resolve qualified canonical endpoint facts`

Committed host source matched the deployed runtime source.

## Documentation impact

This work materially changed reusable conversational resource interpretation.

Updated owners:

- ADR-006;
- Resource Inquiry / Evidence Pattern;
- Extension Construction Map;
- CURRENT resume point;
- this proof record.

No runtime runbook change was required.

No new production entity or capability was introduced, so no System Registry mutation was required.

## Remaining boundary

Fail-closed ambiguity is correct but currently returns generic `conversation_unresolved`.

The next workstream may provide a bounded clarification such as asking whether the human means LAN/private or WAN/public.

That future work must preserve:

- no provider access before disambiguation;
- no orchestration of the ambiguous request;
- no model guess;
- governed candidate facts only;
- authenticated conversation identity;
- auditability;
- existing no-bypass rules.

## Result

Canonical-fact qualifier resolution is live-proven and durable.

Qualified LAN/WAN wording resolves deterministically.

Bare and conflicting wording fails closed.

Operational provider facts remain outside the qualifier layer.
