# DNSFilter Dual-Plane Integration — 2026-09-24

## Purpose

Project Jason integrates DNSFilter through two provider-supported surfaces with different operational roles.

- **REST posture/evidence plane** — deterministic unattended reads from `https://api.dnsfilter.com`.
- **DNSFilter MCP investigation/admin plane** — provider-supported MCP at `https://mcp.dnsfilter.com/mcp` using per-user OAuth.

Central Orchestrator remains authoritative. Neither provider credential nor DNSFilter's own `confirm: true` field creates Jason authority.

## Provider evidence reviewed

DNSFilter's current MCP documentation states:

- MCP server URL: `https://mcp.dnsfilter.com/mcp`;
- per-user OAuth;
- Core, Plus, or Enterprise plan required;
- re-authentication every 7 days;
- Admin, DNS Reporting, and CyberSight capability areas;
- DNS Reporting is read-only;
- privacy mode is enforced by DNSFilter;
- every provider write requires explicit in-conversation confirmation;
- reads are instrumented and writes are attributable to the authenticated user;
- MSP use requires organization scoping.

On 2026-09-24, Jason also performed an unauthenticated MCP discovery/list-tools probe against the public provider contract. DNSFilter identified the server as `dnsfilter-public` version `0.6.0`, protocol `2025-06-18`, and advertised 107 tools. The public contract snapshot is stored at:

`docs/reference/DNSFilter-MCP-Tool-Catalog-2026-09-24.json`

Twenty-five tools currently advertise a required `confirm: true` field. Those write tools are deployed as dormant `BUILDING` capability definitions behind the dedicated `dnsfilter_mcp_mutation` provider, which remains `PLANNED / UNKNOWN / BLOCKED` with no mutation invoker registered unless an explicit mutation activation profile and execution gate are both enabled.

## REST posture plane

Provider ID: `dnsfilter`

Logical secret: `dnsfilter.readonly`

Provider host: `https://api.dnsfilter.com`

Current production-accepted read capabilities:

- `dns.protection.organization.read`
- `dns.protection.site.search`
- `dns.protection.policy.search`
- `dns.protection.agent.search`
- `dns.protection.agent.counts.read`

REST is intended for scheduled client posture reviews, site/network coverage, policy inventory, roaming-client state, expected protective-DNS coverage, and client-security-posture evidence.

The connector rejects caller-supplied DNSFilter organization/MSP identifiers. The exact organization ID comes from a validated Jason boundary mapping the Autotask company ID to the DNSFilter organization ID.

## MCP investigation/read plane

Provider ID: `dnsfilter_mcp`

OAuth server/resource: `https://mcp.dnsfilter.com/`

OAuth completion uses the DNSFilter-supported loopback redirect pattern `http://127.0.0.1:<port>/oauth/callback`. During production acceptance, DNSFilter dynamic registration rejected the custom public Jason callback URI, so Jason used a temporary local-port tunnel to a one-shot callback listener instead.

Durable OAuth state: `/var/lib/jason/openclaw/dnsfilter-mcp/oauth.sqlite3`

The OAuth database is mode `0600`, contains the dynamic OAuth client registration, short-lived PKCE transaction state, and OAuth token material, and is never returned through MCP/tool output.

Current provider-neutral read capabilities:

- `dns.investigation.query.search`
- `dns.investigation.query.explain`
- `dns.investigation.blocked.traffic.search`
- `dns.investigation.anomaly.search`
- `dns.protection.agent.stale.search`
- `dns.protection.agent.version.report`
- `dns.protection.agent.duplicate.search`
- `dns.protection.site.drift.search`
- `dns.protection.policy.category.search`
- `dns.protection.unblock.request.search`
- `dns.protection.unblock.request.count.read`

Each call starts from an exact Autotask company ID, resolves the validated DNSFilter organization boundary, rejects caller-supplied `organization_id`, `organization_ids`, `msp_id`, and `confirm`, injects the mapped provider organization ID, invokes one fixed allowlisted DNSFilter MCP tool, records provider/tool/client scope in Jason audit evidence, and rejects a response if an included organization identifier crosses the mapped boundary.

There is no generic arbitrary DNSFilter MCP tool capability.

## MCP OAuth lifecycle

The provider uses OAuth Authorization Code + PKCE.

Local lifecycle helper:

`python3 tools/dnsfilter_mcp_oauth.py status`

Start/re-authenticate:

`python3 tools/dnsfilter_mcp_oauth.py start`

The command dynamically registers or reuses the Jason OAuth client, creates a short-lived state/PKCE transaction, and prints the DNSFilter authorization URL. It never prints tokens or the PKCE verifier.

After the authenticated user approves the DNSFilter sign-in, DNSFilter redirects to the registered loopback callback. During the 2026-09-24 acceptance, Jason used a temporary SSH loopback tunnel so the browser redirect reached a one-shot Jason callback listener without exposing the authorization code in chat. The callback validates state/issuer, exchanges the code, and stores the resulting tokens.

Verify:

`python3 tools/dnsfilter_mcp_oauth.py verify`

If refresh fails or the provider's periodic re-authentication requirement is reached, runtime calls fail closed with a re-authentication-required condition. Jason must not fall back to a different account or unmanaged token.

## Credential acquisition walkthrough

### REST API key

DNSFilter's current API-key documentation says API keys are user-scoped, inherit the permissions of the user who creates them, are limited to five active keys per user, and are shown in full only once at creation. DNSFilter recommends that account owners avoid creating API keys when a lower-privilege user can satisfy the integration.

When we activate REST:

1. Sign in to the DNSFilter dashboard using the dedicated/least-privilege account selected for Jason.
2. Open **Account Settings**.
3. Open the **Security** tab.
4. Scroll to **API Keys**.
5. Select **+ Create Key**.
6. Name the key `Project Jason REST Read` (or another clearly Jason-specific name).
7. Choose an expiration consistent with AOT credential-rotation policy.
8. Select **Generate Key**.
9. Copy the key exactly once. Do **not** paste it into chat, Git, a ticket, or shell history.
10. Jason's secret-provisioning flow will write it directly to the isolated OpenBao path `secret/data/connectors/dnsfilter/production/read-only` under logical name `dnsfilter.readonly`.
11. Save the key in DNSFilter after the OpenBao write has been verified without revealing the value.

Source: https://help.dnsfilter.com/hc/en-us/articles/21169189058323-API-Keys

The REST credential is not authorization. Jason still requires explicit read authority and a validated company-to-DNSFilter-organization boundary.

### MCP OAuth

DNSFilter's current MCP documentation requires an account with admin permissions or higher, an eligible Core/Plus/Enterprise plan, and interactive OAuth. Re-authentication is required every seven days.

When we activate MCP:

1. Confirm the DNSFilter account to authenticate. Prefer a dedicated Jason administrative identity if AOT wants provider-side actions attributed to Jason; otherwise use the named administrator account AOT chooses for the pilot.
2. On Jason, run:
   `python3 tools/dnsfilter_mcp_oauth.py status`
3. Start the OAuth ceremony:
   `python3 tools/dnsfilter_mcp_oauth.py start`
4. Jason performs OAuth metadata verification, dynamically registers/reuses the Project Jason public client, creates a short-lived PKCE transaction, and prints **only** the authorization URL.
5. Open that URL in a normal browser.
6. Sign in to DNSFilter. If AOT uses DNSFilter SSO, enter only the SSO key when DNSFilter asks for it, as documented by DNSFilter.
7. Complete the provider OAuth approval and select the intended organization context when prompted.
8. DNSFilter redirects to the registered loopback URI. Use a temporary SSH local-port tunnel to the one-shot callback listener on Jason; do not paste authorization codes into chat.
9. Jason validates state and issuer, exchanges the authorization code, and stores the OAuth registration/token material in the private mode-0600 OAuth database. The browser receives only a connected/error status; tokens are never displayed.
10. Verify from Jason:
    `python3 tools/dnsfilter_mcp_oauth.py verify`
11. Perform a controlled read against one known client before any MCP capability is promoted from PILOT.

Source: https://help.dnsfilter.com/hc/en-us/articles/53848353153555-DNSFilter-MCP-connector

The OAuth session does not authorize DNSFilter writes in Jason. All provider write tools remain dormant until separately reviewed and granted.

## MCP administrative/write plane

The 2026-09-24 provider tool catalog exposes 25 confirmation-gated writes including policy allow/block-list changes, category/global-list changes, policy clone/create/update/delete, site policy assignment, portal-user administration, roaming-client policy reassignment/uninstall, bulk agent removal, site forwarder changes, block-page changes, and unblock-request decisions.

All 25 are mapped in `implementation/orchestrator/dnsfilter_mcp_mutation_capability_catalog.py`. By default they remain `BUILDING`; the dedicated `dnsfilter_mcp_mutation` provider remains `PLANNED / UNKNOWN / BLOCKED`; and no mutation invoker is registered.

Promotion of any write requires exact client/organization resolution, exact target-resource resolution, fixed provider tool mapping, normalized payload binding, stable intent/execution-plan fingerprints, explicit owner/technician approval, provider `confirm: true` only after Jason approval, exactly one provider mutation invocation, provider-native post-write readback, unknown-outcome handling without blind retry, Autotask documentation, and rollback/recovery semantics where possible.

Operations that can interrupt filtering, DNS resolution, endpoint protection, or user access remain user-disruptive and require explicit technician approval under the Project Jason governance rule.

## Production activation gates

### REST

1. dedicated least-privilege DNSFilter API key;
2. `dnsfilter.readonly` OpenBao provisioning;
3. exact Autotask-company-to-DNSFilter-organization boundaries;
4. explicit `provider-read:dnsfilter` observe authority;
5. controlled production read acceptance;
6. `JASON_DNSFILTER_ENABLED=true`;
7. promote accepted canonical read capabilities from PILOT to ACTIVE.

### MCP reads

1. source merged and deployed;
2. OAuth callback publicly reachable;
3. authenticated AOT DNSFilter admin OAuth session established;
4. exact client boundaries present;
5. explicit `provider-read:dnsfilter_mcp` observe authority;
6. controlled organization-bounded read acceptance;
7. `JASON_DNSFILTER_MCP_ENABLED=true`;
8. promote accepted canonical MCP reads from PILOT to ACTIVE.

### MCP writes

No write is activated by the read deployment. Each write family requires a separate governed mutation acceptance and explicit authority grant.

For the first controlled production write acceptance, use the narrow profile:

- `JASON_DNSFILTER_MCP_MUTATION_PROFILE=policy_create_acceptance_v1`
- `JASON_DNSFILTER_MCP_MUTATION_ENABLED=true`

That profile activates and registers only `dns.protection.policy.create`. The other 24 DNSFilter mutation capabilities remain `BUILDING` and have no invoker registration. For MCP discovery/execution, each mutation definition publishes bounded resource/operation metadata plus `mcp_action_enabled=true`; lifecycle remains the controlling exposure gate, so only an `ACTIVE` capability appears. The policy-create capability additionally allows the authenticated owner’s exact conversational imperative to satisfy the approval signal. The authenticated owner must also have a narrow `execute` authority grant for `dns.protection.policy.create` with `approval_required=true`.

The broader `governed_v1` profile exists for a future separately approved full-write activation and must not be used for the first acceptance test.

## Failure rules

- Never infer authority from DNSFilter account role alone.
- Never accept provider organization/MSP scope from the caller.
- Never expose the generic provider tool catalog as executable authority.
- Never automatically set `confirm: true` for a write without an approved Jason execution plan.
- Never retry a write after an unknown outcome unless provider readback proves it did not occur.
- Never bypass DNSFilter privacy mode.
- Never silently switch authenticated DNSFilter users.
- Never treat OAuth expiry as provider outage; require re-authentication.

## Production read acceptance — 2026-09-24

The read-only integration is accepted and live.

- Autotask self-company `0` (`Atlantic Office Machines`) is mapped to DNSFilter organization `1110483` (`Atlantic Office Technologies`).
- REST and MCP read providers are enabled, `AVAILABLE`, `HEALTHY`, and `APPROVED`.
- DNSFilter read capabilities are `ACTIVE`.
- sixteen `observe` grants exist for the authenticated AOT owner identity; there are no DNSFilter execute/administer grants.
- REST acceptance succeeded after adding `User-Agent: Mozilla/5.0 Project-Jason-DNSFilter-REST/1.0`; without it DNSFilter's Cloudflare edge returned Error 1010 / browser-signature blocked.
- MCP OAuth verification succeeded and provider reads were accepted against organization `1110483`.
- DNSFilter writes remain unavailable. The deployable write foundation may register them only as dormant `BUILDING` definitions behind a `PLANNED / BLOCKED` mutation provider; no write invoker, authority grant, or active write provider exists unless the separate mutation gates are explicitly enabled.

The deployable dormant read/write design and its separate activation/acceptance gates are documented in `DNSFilter-Full-Read-Write-Design-2026-09-24.md`.

## First write-acceptance attempt — fail-closed result

The first production policy-create acceptance attempt correctly stopped before provider mutation because the write foundation was deployed dormant: `dns.protection.policy.create` was `BUILDING`, `dnsfilter_mcp_mutation` was not available to normal governed-action discovery, and no mutation invoker was registered. The pre-read successfully validated Autotask company `0` -> DNSFilter organization `1110483`, returned the current policy inventory, and found no exact match for the requested test-policy name. Provider mutation invocation count was `0`, ordinary DNSFilter reads remained available, and no configuration or assignment changed.

The corrective control-plane design is the narrow `policy_create_acceptance_v1` profile described above. This avoids activating all 25 administrative writes merely to perform the first controlled create-policy acceptance.

## Successful policy-create acceptance

The bounded production policy-create acceptance subsequently passed with exactly one provider mutation attempt. DNSFilter policy `1506474` (`Jason DNSFilter Governed Write Test 2026-09-24`) was created under organization `1110483` with no network, agent, local-user, or collection assignment. The provider returned an error after the mutation, so Jason did not retry; provider-native readback proved the policy inventory increased from 39 to 40 and resolved the exact created policy. The full acceptance evidence is recorded in `DNSFilter-Policy-Create-Acceptance-2026-09-24.md`.

The acceptance also established that DNSFilter mutation execution plans must use provider-relative paths such as `/tools/create_policy`, not `mcp://dnsfilter/tools/create_policy`.

Post-test cleanup semantics are fail-safe: `JASON_DNSFILTER_MCP_MUTATION_ENABLED=false` or unset leaves the mutation foundation healthy and dormant even if the acceptance profile string remains present. A true execution gate with no valid profile still fails closed.

## Current post-acceptance production state

As of the completed cleanup deployment on revision `7a74946637077edf69df34a555429c5fa873e086`, DNSFilter writes are fully dormant again: execution gate `false`, all 25 mutations `BUILDING`, provider `PLANNED / UNKNOWN / BLOCKED`, zero DNSFilter mutation invokers, and the policy-create acceptance grant inactive. `dns.protection.policy.create` is no longer present in Jason's live write-capability catalog. DNSFilter reads remain healthy, and the intentionally retained acceptance policy `1506474` is still unassigned.
