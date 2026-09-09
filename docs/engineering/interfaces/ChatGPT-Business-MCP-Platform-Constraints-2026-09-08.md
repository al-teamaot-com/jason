# ChatGPT Business MCP Platform Constraints — Verified 2026-09-08

**Status:** Supporting implementation research  
**Date verified:** 2026-09-08  
**Owner:** Platform Owner / Technology Steward  
**Purpose:** Record current OpenAI product constraints that materially affect MCP-001/MCP-002. These are external product facts and must be re-verified before production publication because the feature is beta and may change.

## Authoritative external sources reviewed

OpenAI Help Center:

- `https://help.openai.com/en/articles/12584461` — Developer mode and MCP apps in ChatGPT
- `https://help.openai.com/en/articles/12515353` — Build with the Apps SDK
- `https://help.openai.com/en/articles/11487775` — Apps in ChatGPT

OpenAI Business Apps overview:

- `https://openai.com/business/apps/`

## Verified current constraints

### Availability

Full MCP support and developer mode are currently available to ChatGPT Business and Enterprise/Edu on **ChatGPT web**.

OpenAI describes full MCP, including write/modify actions, as beta/rolling out. Product behavior, permissions, and UI may change.

### Business-plan administration

For ChatGPT Business:

- only workspace admins/owners can use developer mode and deploy/publish a custom app;
- each admin/owner enables developer mode for themselves;
- Business does not currently provide the Enterprise/Edu-style RBAC controls for selecting individual developers or per-app user groups;
- after publication, Business has less granular action/access control than Enterprise/Edu.

This is material to Jason's pilot scope design. The pilot must not assume Enterprise-style RBAC exists on Business.

### App configuration flow

Current flow:

1. enable developer mode;
2. Workspace settings → Apps → Create;
3. provide MCP server endpoint and metadata;
4. choose authentication mechanism if applicable;
5. Scan Tools;
6. complete OAuth authorization if used;
7. create draft;
8. test draft in ChatGPT;
9. admin/owner publishes from Workspace settings → Apps.

### OAuth / OIDC

If OAuth/OIDC is used, persistent connectivity requires refresh-token support.

OpenAI specifically recommends that OIDC providers advertise/support `offline_access` (or provider equivalent) and issue refresh tokens. If refresh tokens are unavailable, users may need to reauthenticate after the original authorization expires.

Jason's identity design must account for this before selecting OAuth/OIDC.

### Remote server requirement

ChatGPT does **not** connect directly to a local MCP server.

OpenAI currently states that ChatGPT connects to **remote MCP servers**. For an MCP server running on a private network, on-premises environment, or developer machine, OpenAI recommends **Secure MCP Tunnel** rather than exposing the server directly to the public Internet.

This materially affects the Jason host design: the initial Jason MCP service cannot remain reachable only at `localhost`/private Docker networking if ChatGPT is expected to use it directly. The preferred next investigation is the Secure MCP Tunnel pattern versus another approved remote ingress design.

### Tool requirements

Custom MCP servers no longer require `search` and `fetch` tools specifically. Jason can expose its governed capability-oriented tools directly.

This supports the current Jason plan to project meaningful capability-derived tools rather than constructing artificial search/fetch wrappers solely for ChatGPT compatibility.

### Multiple apps

ChatGPT can invoke multiple first-party and third-party apps in a single prompt.

This means Jason may remain one governed app while technicians can also use other approved workspace apps. Jason should not assume it exclusively owns all model tools available in a ChatGPT turn.

### App selection / follow-up behavior

App selection applies to the message where the app is used. Results already returned remain available in the conversation, but a follow-up that needs new Jason data/action may require the Jason app to be invoked/mentioned again.

Pilot testing must validate this actual technician experience rather than assuming the app stays actively selected for every message in a conversation.

### Business publication/update behavior

Important Business-plan constraint:

- at current launch behavior, a published Business custom app cannot simply be updated in place like an Enterprise/Edu app;
- changing tools or metadata requires recreation/republishing;
- OpenAI uses a frozen snapshot of approved tool definitions/inputs;
- live server tool-definition changes are not automatically adopted;
- incompatible tool-schema changes can cause calls to fail until the workspace app is refreshed/republished.

This has direct architecture implications:

1. keep the initial Jason MCP tool contract small and stable;
2. version tool schemas deliberately;
3. avoid frequent breaking tool-definition changes during pilot;
4. separate backend implementation evolution from public MCP schema evolution;
5. document republish/rollback procedure.

### Mobile

Current OpenAI documentation states MCP apps are not available on mobile; the supported custom-app experience is web-only.

The initial Jason pilot should therefore target technicians using ChatGPT web. Desktop/mobile support must be separately verified before being claimed.

### Write actions

Custom MCP apps can support write/modify actions. ChatGPT may request confirmation depending on app permissions/action context, and some risky actions may be blocked.

Jason must not rely on ChatGPT confirmation as a substitute for Jason authorization/approval. Jason's own deterministic action governance remains controlling.

Initial Jason pilot remains read-only.

### Company knowledge / deep research / agent mode

Current constraints include:

- company knowledge can use custom apps with search/fetch access;
- deep research can use custom apps for read/fetch, not write actions;
- agent mode does not use custom apps in the same way described for normal chats;
- Workspace Agents have their own tool/app controls.

These are adjacent possibilities, not part of MCP-001's initial normal-chat design.

## Security implications for Jason

OpenAI explicitly warns that untrusted MCP servers increase prompt-injection and related risk. AOT is responsible for vetting its custom app/server.

Jason must therefore continue to enforce:

- server-side capability allowlists;
- identity binding;
- client/tenant isolation;
- no secret exposure;
- no arbitrary provider URL execution;
- policy/approval boundaries;
- tool input validation;
- evidence/result sanitization;
- audit/provenance;
- read/write separation;
- disable/rollback.

Do not rely on ChatGPT app approval alone as Jason's security boundary.

## Immediate design consequences

The next implementation decisions should be based on these verified facts:

1. **Remote connectivity is required.** Investigate OpenAI Secure MCP Tunnel first for the on-prem Jason host rather than publishing a raw public endpoint by default.
2. **Business admin controls are coarser than Enterprise/Edu RBAC.** Keep Jason server-side identity/authorization authoritative and pilot exposure conservative.
3. **Tool schemas should be stable.** Business publication/republish behavior makes a small versioned initial surface preferable.
4. **OAuth/OIDC must support refresh tokens** if selected for end-user authentication.
5. **Pilot is ChatGPT web first.** Do not promise mobile until re-verified.
6. **Read-only remains the correct initial boundary.** ChatGPT's write confirmations are supplemental, never substitutes for Jason governance.
7. **No artificial search/fetch wrapper is required.** Capability-oriented MCP tools can remain the target design.

## Reverification rule

Before pilot publication and before any material later expansion, re-open the current official OpenAI documentation because full MCP support is beta and these constraints may change.
