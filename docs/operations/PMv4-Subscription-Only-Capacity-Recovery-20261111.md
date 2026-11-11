# PMv4 subscription-only capacity recovery — preproduction evidence

**Scope:** Source-only PMv4 branch stacked on draft PR #2426, which is stacked on draft PR #2421. This is not a production deployment, scheduler installation, agent restart, or authorization to replay background tasks.

## Governing contract

The Owner-approved PMv4 outline, section 9, requires use of the existing OpenAI ChatGPT subscription through supported authentication, **not** separately billed OpenAI API use, third-party providers, additional subscriptions, or automatic metered fallback. It also requires verifying subscription authentication, concurrency and usage limitations.

## Live read-only findings (2026-11-11, 18:34–18:45 UTC)

- OpenClaw 2026.7.1 on Jason: both J-Man and J-Dev report openai/gpt-5.6-sol as the sole allowed model, with no fallbacks.
- Both report runtime=codex, authProvider=openai, kind=profiles; the auth profile summary reports one OAuth profile, zero API-key profiles and zero token profiles. No API-key environment-variable names were found in the gateway process. **The name codex is the runtime transport label, not evidence of separately billed Codex API calls.** These checks describe configuration, not independent invoice/billing verification.
- The native OpenClaw tasks maintenance preview reported 35 terminal tasks (28 succeeded, six failed, one timed out), zero active tasks and zero automatically recovered tasks. It does not resume quota-failed development assignments.
- The native task ledger contains quota-failed J-Man development assignments and a failed J-Dev engineering run. Two native records (CLI + subagent) can refer to the same run ID: **never resubmit both**.
- The recorded provider error suggested a subscription reset on **2026-11-11 at 16:24 EST**. This is a scheduling *hint*, not independent proof that capacity has returned.

## Supported OpenAI subscription access (verified documentation)

Current OpenClaw and OpenAI documentation distinguish Codex OAuth and Sign in with ChatGPT (SIWC Beta). Both can use a ChatGPT account without an API key; SIWC also spends an eligible Work/Codex allowance, not an unlimited pool of ordinary ChatGPT conversation messages. Switching to SIWC would not prove capacity after the observed Codex subscription rate limit and could require separate account/workspace consent. It must not be silently enabled or treated as a quota bypass.

- https://docs.openclaw.ai/providers/openai/authentication
- https://docs.openclaw.ai/providers/openai/setup
- https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites

## Source-only correction

- tools/pmv4_subscription_capacity.py checks the OAuth-only route shape and rejects API-key, token, extra-provider and metered-fallback routes. It never reads credentials or makes API calls.
- It classifies a verified native subscription-usage failure separately from generic failed work, preserves the provider reset time strictly as a hint, and deduplicates CLI/subagent ledger views by agent and run ID.
- tools/pmv4_workboard_reconciliation.py now holds quota-exhausted native work rather than converting it into generic terminated-work recovery eligibility.
- A trusted fresh native OpenClaw model probe can be interpreted as capacity available or rate limited only when the OAuth-only route matches. It never grants replay authority. An isolated read of the actual November 11 probe returned SUBSCRIPTION_OAUTH + WAIT_QUOTA_RESET.
- Focused PMv4 acceptance: 53 passed, 5 skipped, 25 subtests passed; no existing production services or configuration modified.
- The correction intentionally **does not** mutate OpenClaw configuration, claim work, retry native tasks, call a provider, or decide that model capacity is available without a successful fresh provider probe.

## Integration and release acceptance still required

1. Trusted, read-only runtime adapter obtains fresh agent-specific OpenClaw model status and native tasks show data through the existing CLI. Do not accept Workboard/user-supplied error strings as proof.
2. When the provider-supplied reset hint has elapsed, verify OAuth subscription capacity with the supported existing authentication route, **without** setting any API key or enabling paid fallback.
3. Re-read native task identity, Workboard claim/status/attempts, PMV3 exact-action authority, retry budget, idempotence and durable receipts. Only the existing governed work engine may dispatch one permissible task after successful revalidation. An unlinked CLI task is not automatically replayable.
4. Verify a previously quota-blocked controlled development task produces a new authenticated native run ID, new source commit or tests, and independent acceptance. Confirm no duplicate replay after interruption.
5. Confirm existing ticket processing, protected Core services, production freeze, release hold and original provider policies remain unchanged.
6. Prepare exact release SHA, scope, existing working production baseline, rollback SHA and evidence. Obtain separately governed release authority **before** production deployment.

**Current operating limitation:** Authenticated subscription capacity is exhausted for the identified runs; this source-only correction prepares fail-closed recovery but does not itself cause J-Man to resume work. Do not report PMv4 operational recovery until a real authenticated task finishes and its output is independently verified.
