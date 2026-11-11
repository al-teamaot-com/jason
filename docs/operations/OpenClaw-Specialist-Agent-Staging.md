# OpenClaw specialist agents — preproduction staging

## Scope and safety
This commit supplies six role profiles and a shared contract for **offline** setup: j-compliance, j-docs, j-observe, j-qa, j-integrations, j-release. The already-existing main, j-man, and j-dev agents are not changed. No runtime config, gateway binding, credentials, scheduler, Teams approvals, provider access, feature activation, or production releases are changed.

The source manifest is authoritative for intended roles. Specialists are work executors, not new process gates. J-Man retains task ownership. Only impacted specialists should run, preferably in parallel. Core services and unrelated ticket processing must remain untouched.

## Preproduction acceptance
1. Verify six independent workspace identities, no routing rules, no production tool grants, and correct existing OpenAI/Codex model mapping.
2. Prove agent creation in an isolated OpenClaw state directory, **not** the active gateway state. Do not import/copy real OAuth tokens into staging.
3. Validate each specialist's role handoff and a harmless offline exercise; do not claim subscription-funded agent execution without verifying its own OAuth on an authorized test surface.
4. Verify J-Man can delegate to an authorized specialist through supported OpenClaw routing and that durable Workboard state resumes an interrupted task. Existing PR #2382 is a related dependency, not authority to activate.
5. Verify existing PMV3.2 release and ticket-processing functionality remain active and unchanged.
6. When ready, prepare one governed component-scoped release package and obtain existing exact-release authority. The proposed future one-upfront-approval lifecycle requires an approved amendment; it is not currently enabled.

## Rollback and non-disruption
Delete only the isolated preproduction state directory to revert the staging exercise. Source rollback is by Git revert. Do not restart or mutate the production OpenClaw gateway. All production activation remains separate and approval-bound.
