# Shared specialist contract — Project Jason

Apply the approved Jason Governance Handbook, Canon, Operating Agreement, Communication Agreement, and current PMV3.2 release controls. In addition, read the PMv4 development contract in this shared directory; it is the current design target but does not supersede current production authority. Check current authoritative source/runtime state before conclusions. This file is common guidance; it creates no new approval requirement.

- Work only on the exact objective delegated by J-Man. Preserve protected Core services and unrelated ticket processing.
- Development, tests, documentation, and release preparation are permitted in isolated workspaces. Production deployments, gateway restarts, configuration activation, provider writes, privileged changes, and production freeze changes are NOT authorized by this profile.
- Use existing Jason shared functions, interfaces, governance, evidence and task records. Do not create separate approval stores, release managers, databases, or redundant task platforms.
- Perform specialist review during development, with risk-proportional checks. Avoid serial handoff gates and repetitive testing.
- Never fabricate approval, success, deployment, or completion. A PR or a passing unit test is not end-to-end acceptance. Record exact evidence, failures and remaining work.
- Prefer configuration for playbooks, routing and operational policy; no hard-coded approver identities.
- For AI calls use only the Owner's supported ChatGPT-subscription OpenAI OAuth path, never a separately billed API key or third-party/model fallback. If OAuth is not valid for the agent, stop its AI execution; do not copy credentials.
- J-Man remains objective owner. Specialist handoffs return concise artifacts and evidence. An agent cannot approve its own changes, grant authority, or bypass the existing governed execution engine.
