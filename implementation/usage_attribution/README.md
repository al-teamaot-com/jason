# Jason Usage Attribution

Jason usage attribution answers four operational questions for observable external-resource consumption:

1. Who or what caused the use?
2. Why was it used?
3. Which provider/product/service was consumed?
4. What usage, billing class, cost, and correlation evidence is available?

The attribution context is accounting/audit metadata only. It never grants authority, chooses a provider, or changes organization/client scope. Human identity is represented by Jason's stable principal identity, with email/display name as optional trusted display metadata. Workloads use explicit named service/agent/scheduled-process identities.

Raw prompts, provider responses, credentials, bearer tokens, API keys, OAuth tokens, and secrets are excluded from attribution telemetry.

Model usage continues to be written through `implementation/usage_ledger`; when a generic attribution scope is bound, the model ledger projects actor, source/channel, purpose, correlation, and friendly identity metadata into the immutable usage entry. Provider/API operations that expose only request counts or subscription/included usage should be retained with unavailable units/cost rather than fabricated values.
