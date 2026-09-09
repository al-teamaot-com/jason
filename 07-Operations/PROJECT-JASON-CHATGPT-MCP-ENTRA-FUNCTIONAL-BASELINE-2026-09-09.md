# Project Jason — ChatGPT MCP + Microsoft Entra Functional Baseline

**Date:** 2026-09-09  
**Branch:** `feature/jason-runtime-service`  
**Status:** End-to-end functional baseline achieved in the dedicated MCP pilot. ChatGPT can authenticate through Microsoft Entra, discover and invoke Jason's governed read interface, and return live governed operational evidence. Production/runtime promotion is **not** part of this checkpoint.

## Executive summary

Project Jason has successfully gained a second governed conversational client surface: **ChatGPT**.

A ChatGPT custom app now reaches Jason through the public MCP endpoint at:

`https://mcp-jason.teamaot.com/mcp`

The working path is:

`ChatGPT -> OAuth 2.0 / PKCE -> Microsoft Entra ID -> Jason MCP -> Jason identity/authority -> Central Orchestrator -> authorized read capability -> governed evidence -> ChatGPT response`

This is significant because ChatGPT is **not** connected directly to Datto RMM or another provider. The MCP service remains a thin governed interface into Jason. Jason identity, authority, capability policy, provider access, evidence boundaries, and Central Orchestrator execution remain authoritative.

The first demonstrated end-to-end operational proof from ChatGPT was:

- request: `who is logged into aot-50282`
- ChatGPT source/app: `Jason-09092026-2`
- returned endpoint: `AOT-50282`
- returned last logged-in user: `AzureAD\\AlDavis`
- returned device state: online

That proof demonstrated substantially more than OAuth success: ChatGPT authenticated, entered Jason through MCP, invoked Jason's governed read surface, obtained live endpoint evidence, and produced a grounded operational answer.

This checkpoint should be read alongside the prior [Teams + Datto RMM Functional Baseline](PROJECT-JASON-TEAMS-DRMM-FUNCTIONAL-BASELINE-2026-08-28.md). The same architectural principles continue to apply: capability-driven execution, resource identity preservation, governed evidence, and no question-specific routing hard-coding.

---

## Objective

Establish a secure, read-only, Microsoft Entra-authenticated MCP interface so ChatGPT can use Project Jason as a governed operational source without bypassing Jason's existing authority or provider controls.

The acceptance goal was not merely to make an MCP endpoint respond. The complete requirement was:

1. ChatGPT can reach the public MCP URL.
2. Unauthenticated access is rejected correctly.
3. ChatGPT can discover OAuth metadata from Jason.
4. Microsoft Entra authenticates the caller.
5. ChatGPT obtains a token for the Jason resource and delegated `Jason.Read` permission.
6. Jason validates the Entra token and maps the Microsoft identity into Jason authority.
7. ChatGPT can discover Jason's MCP tools.
8. Tool execution remains read-only and flows through the Central Orchestrator.
9. Provider credentials and direct provider access are not exposed to ChatGPT.
10. A real operational question returns live governed evidence.

All ten conditions were demonstrated by the functional baseline.

---

## Scope and isolation

This work was intentionally isolated to the dedicated MCP pilot and Entra application registrations.

### MCP pilot

- container: `jason-mcp-pilot`
- image: `jason-mcp:entra-pilot`
- container port: `8000`
- host mapping observed during the checkpoint: `10.87.246.157:8765 -> 8000`
- public URL: `https://mcp-jason.teamaot.com/mcp`
- health URL: `https://mcp-jason.teamaot.com/healthz`

### Runtime isolation

The existing `jason-runtime` production container and the isolated conversation-experience candidate containers, including V8.10.2, were not promoted or modified as part of this MCP integration checkpoint.

The MCP accomplishment is therefore a **new governed client ingress**, not a production conversation-runtime promotion.

---

## MCP tool surface

The MCP pilot intentionally exposes a very small tool surface:

### `jason_mcp_status`

Returns MCP pilot state and confirms the interface is:

- read-only;
- centrally governed;
- not a direct provider interface;
- not write-enabled.

Representative server state includes:

- `mode = read-only`
- `phase = governed-read-pilot`
- `governed_execution = central-orchestrator`
- `direct_provider_access = false`
- `write_tools_enabled = false`

### `discover_capabilities`

Discovers Jason's **currently active governed read capabilities** from the live capability registry rather than presenting ChatGPT with a large fixed provider-specific task list.

This preserves the core Jason design: model-facing clients discover structured capability contracts while Jason remains responsible for authority and execution.

### `execute_read_capability`

Executes one capability that is currently:

- active;
- read-only;
- present in Jason's live capability registry;
- authorized through Jason governance.

The call proceeds through Jason identity/authority and Central Orchestrator execution. Provider credentials are never returned to ChatGPT.

---

## Microsoft Entra application architecture

Two Entra applications have distinct roles.

### Resource/API application — `Jason MCP API`

- Application (client) ID: `9b9996e9-5c34-48b7-948c-f44f89352f89`
- original Identifier URI retained: `api://9b9996e9-5c34-48b7-948c-f44f89352f89`
- canonical MCP Identifier URI added: `https://mcp-jason.teamaot.com/mcp`
- delegated permission name: `Jason.Read`
- delegated permission/scope ID: `daa288b0-1fff-4844-8a98-0250c36a432c`

The canonical OAuth scope requested by ChatGPT is therefore:

`https://mcp-jason.teamaot.com/mcp/Jason.Read`

### ChatGPT OAuth client — `Jason - ChatGPT MCP`

- Application (client) ID: `9bdefd9b-df74-4ac7-801b-8aa610366901`
- Application object ID: `f9d462d2-d015-4073-a878-61bfdef0da3a`
- Service Principal ID: `c3f6d5ff-7dd2-4a1c-a216-99809f7a605d`
- sign-in audience: `AzureADMyOrg`
- OAuth client type used by ChatGPT: user-defined confidential client
- token endpoint authentication: `client_secret_post`
- redirect URI used during the working setup: `https://chatgpt.com/connector/oauth/7fQmizHEEUCJ`

A dedicated client secret exists for this application. **The secret value is intentionally not documented here and must never be committed to GitHub, pasted into tickets, or placed in ordinary documentation.**

The ChatGPT client has delegated access to the Jason API's `Jason.Read` scope.

### Tenant

- Entra tenant ID: `f7054323-d52b-4863-8c2f-1898f0b6077c`

---

## Why two scope representations exist

A key implementation detail is that the OAuth request scope and the access-token `scp` value are related but not identical strings.

### OAuth-facing scope

ChatGPT requests:

`https://mcp-jason.teamaot.com/mcp/Jason.Read`

This is the API Application ID URI plus the delegated permission name.

### Token claim scope

Microsoft Entra emits the delegated permission value in the JWT `scp` claim as:

`Jason.Read`

Jason therefore intentionally maintains two representations:

- `JASON_REQUIRED_SCOPE = Jason.Read` for JWT claim validation;
- `JASON_OAUTH_REQUEST_SCOPE = https://mcp-jason.teamaot.com/mcp/Jason.Read` for MCP/OAuth discovery and authorization.

After validating the real token claim, the MCP token context includes the fully-qualified OAuth scope so the MCP authorization layer can satisfy the scope it advertised to the client.

This separation is required. Changing JWT validation to require the fully-qualified string would incorrectly reject valid Entra tokens.

---

## Token validation and Jason authority

The MCP service uses a dedicated Entra token verifier.

The verifier validates, among other things:

- RS256 signature through Microsoft's JWKS;
- token audience against the Jason MCP API application ID;
- issuer against the AOT Entra tenant issuer;
- token lifetime claims;
- tenant ID (`tid`);
- Microsoft object ID (`oid`);
- delegated `scp` containing `Jason.Read`.

The normalized MCP identity context intentionally minimizes claims and retains only the identity material needed to continue Jason authorization.

Authentication alone does not grant operational authority. The Microsoft tenant/object identity is subsequently resolved through Jason's existing Microsoft identity bindings and authority path.

This preserves the boundary:

**Entra proves who authenticated; Jason decides what that identity is authorized to do.**

---

## OAuth discovery architecture

The largest compatibility challenge was not that Entra lacked OAuth or PKCE. The challenge was satisfying the exact metadata semantics expected by ChatGPT's MCP OAuth client while preserving Entra as the real authorization server.

### Protected resource metadata

Jason publishes:

`https://mcp-jason.teamaot.com/.well-known/oauth-protected-resource/mcp`

The working metadata is conceptually:

```json
{
  "resource": "https://mcp-jason.teamaot.com/mcp",
  "authorization_servers": [
    "https://mcp-jason.teamaot.com/"
  ],
  "scopes_supported": [
    "https://mcp-jason.teamaot.com/mcp/Jason.Read"
  ],
  "bearer_methods_supported": [
    "header"
  ]
}
```

### Jason OAuth compatibility issuer

The authorization-server issuer advertised to MCP clients is:

`https://mcp-jason.teamaot.com/`

This is a metadata/discovery compatibility facade only. Jason does **not** replace Microsoft Entra as the actual OAuth authorization or token issuer.

### Authorization-server metadata

Jason publishes RFC 8414-style authorization-server metadata at:

`https://mcp-jason.teamaot.com/.well-known/oauth-authorization-server`

The important working values are:

```json
{
  "issuer": "https://mcp-jason.teamaot.com/",
  "authorization_endpoint": "https://login.microsoftonline.com/f7054323-d52b-4863-8c2f-1898f0b6077c/oauth2/v2.0/authorize",
  "token_endpoint": "https://login.microsoftonline.com/f7054323-d52b-4863-8c2f-1898f0b6077c/oauth2/v2.0/token",
  "jwks_uri": "https://login.microsoftonline.com/f7054323-d52b-4863-8c2f-1898f0b6077c/discovery/v2.0/keys",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_post",
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"]
}
```

The scope set also includes the Jason delegated scope plus OIDC scopes such as `openid`, `profile`, `email`, and `offline_access`.

### Exact issuer matching

A subtle but important correction was required because the MCP SDK normalized the protected-resource authorization-server URL to include a trailing slash.

The following values must remain exact matches:

`https://mcp-jason.teamaot.com/`

The checkpoint validation explicitly proved:

- protected-resource authorization server = `https://mcp-jason.teamaot.com/`
- authorization-server issuer = `https://mcp-jason.teamaot.com/`
- `EXACT_MATCH = True`
- `S256 = True`

Do not casually remove or normalize the trailing slash in only one of these locations.

---

## Entra OIDC compatibility shim

Microsoft Entra supports authorization-code PKCE with S256, but its tenant OIDC discovery document did not advertise `code_challenge_methods_supported` in the form ChatGPT required during this integration.

The tenant OIDC discovery check returned:

- issuer: correct;
- authorization endpoint: correct;
- token endpoint: correct;
- token endpoint authentication methods: present;
- OIDC scopes: `openid`, `profile`, `email`, `offline_access`;
- `code_challenge_methods_supported`: not advertised.

Jason therefore exposes an OIDC compatibility endpoint:

`https://mcp-jason.teamaot.com/oauth/entra-openid-configuration`

The shim retrieves Entra's real OIDC discovery document, verifies the issuer, and returns the same metadata with:

```json
"code_challenge_methods_supported": ["S256"]
```

injected.

The shim does not replace Entra endpoints and does not mint tokens.

The ChatGPT advanced OAuth configuration uses:

- OIDC enabled: yes
- OIDC configuration URL: `https://mcp-jason.teamaot.com/oauth/entra-openid-configuration`
- OIDC UserInfo endpoint: `https://graph.microsoft.com/oidc/userinfo`

---

## DCR and CIMD

ChatGPT displayed informational warnings that:

- Dynamic Client Registration (DCR) was unavailable because no Registration URL was advertised;
- Client Identifier Metadata Document (CIMD) was unavailable because the server did not advertise it.

These are expected and non-blocking for this implementation because Jason uses a **User-Defined OAuth Client** with a pre-registered Entra application ID and client secret.

The placeholder Registration URL shown by the ChatGPT UI is not part of the working authentication flow and must not be treated as a Jason registration endpoint.

---

## MCP transport security and public host allowlist

Once OAuth discovery progressed far enough for ChatGPT to invoke the public MCP endpoint, the MCP SDK correctly rejected the reverse-proxied public hostname with:

`Invalid Host header: mcp-jason.teamaot.com`

This was caused by the MCP SDK's DNS-rebinding protection, not by Caddy or Entra.

The pilot now explicitly enables DNS-rebinding protection while allowlisting the intended public host.

Working transport-security intent:

```python
TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "mcp-jason.teamaot.com",
        "mcp-jason.teamaot.com:*",
    ],
    allowed_origins=[
        "https://chatgpt.com",
        "https://chatgpt.com:*",
        "https://mcp-jason.teamaot.com",
        "https://mcp-jason.teamaot.com:*",
    ],
)
```

After this change, an unauthenticated public MCP initialize request returned the desired result:

- HTTP `401 Unauthorized`;
- `WWW-Authenticate: Bearer`;
- `resource_metadata="https://mcp-jason.teamaot.com/.well-known/oauth-protected-resource/mcp"`.

That 401 is an acceptance condition: the public host is accepted, the request reaches Jason authentication, and anonymous MCP use remains denied.

---

## ChatGPT app configuration baseline

The working ChatGPT configuration is based on a user-defined OAuth client.

### Core settings

- Server URL: `https://mcp-jason.teamaot.com/mcp`
- Authentication: OAuth
- Registration method: User-Defined OAuth Client
- Client ID: `9bdefd9b-df74-4ac7-801b-8aa610366901`
- Client secret: stored securely; never document value
- Token endpoint auth method: `client_secret_post`
- Default scope: `https://mcp-jason.teamaot.com/mcp/Jason.Read`
- Base scopes: blank
- Resource: `https://mcp-jason.teamaot.com/mcp`

### OIDC settings

- OIDC enabled: yes
- OIDC configuration URL: `https://mcp-jason.teamaot.com/oauth/entra-openid-configuration`
- OIDC UserInfo endpoint: `https://graph.microsoft.com/oidc/userinfo`

### Callback URL rule

Use the **exact callback URL generated by ChatGPT** for the app instance and register that exact URI as an Entra Web redirect URI.

The working callback observed during this checkpoint was:

`https://chatgpt.com/connector/oauth/7fQmizHEEUCJ`

If ChatGPT generates a different callback in a future app instance, the new exact value must be added to the Entra client before completing OAuth.

---

## Troubleshooting chronology and lessons learned

The path to the functional baseline exposed several distinct issues. Keeping them separate is important for future troubleshooting.

### 1. Initial condition — app created with no actions

ChatGPT could reach Jason, but custom app details showed:

`No actions are available for this app.`

The first public MCP probe correctly returned 401 and pointed at protected-resource metadata, proving the endpoint existed but not yet proving OAuth/tool discovery compatibility.

### 2. Canonical resource and Entra API resource were misaligned

Jason advertised the MCP resource URL while the Entra API initially used only the default `api://<application-id>` Identifier URI.

Resolution:

- retained the original `api://...` Identifier URI;
- added `https://mcp-jason.teamaot.com/mcp` as an additional Identifier URI;
- used the fully-qualified delegated scope `https://mcp-jason.teamaot.com/mcp/Jason.Read` for OAuth requests.

### 3. Device-code testing was the wrong validation path

A direct device-code test failed because the ChatGPT client is a confidential Web client and Entra required a `client_secret` or assertion.

Lesson:

Do not use device-code flow as the primary test of the ChatGPT OAuth registration. ChatGPT's real flow is authorization-code based, and the confidential client configuration should be validated through that path.

### 4. Entra's OIDC document did not advertise S256

Entra supported the needed behavior but did not advertise `code_challenge_methods_supported` in its tenant discovery response.

Resolution:

Added the Jason OIDC compatibility shim and advertised `S256`.

### 5. Protected-resource metadata still pointed directly to Entra

Even after the shim existed, ChatGPT stopped after fetching the protected-resource metadata because `authorization_servers` still told it to discover the Entra issuer directly.

Resolution:

Jason became the OAuth metadata compatibility issuer while continuing to point actual authorization/token operations to Entra.

### 6. Issuer trailing slash mismatch

The protected-resource metadata returned:

`https://mcp-jason.teamaot.com/`

while the authorization-server metadata initially returned:

`https://mcp-jason.teamaot.com`

Resolution:

Made both issuer values exactly:

`https://mcp-jason.teamaot.com/`

Validation subsequently returned `EXACT_MATCH = True`.

### 7. MCP SDK rejected the reverse-proxied public host

Once ChatGPT progressed to MCP transport, Jason returned:

`Invalid Host header: mcp-jason.teamaot.com`

Resolution:

Added an explicit MCP transport host/origin allowlist while leaving DNS-rebinding protection enabled.

### 8. Patched source was not the module loaded by PID 1

The pilot container's PID 1 command was:

`/usr/local/bin/python3.12 /usr/local/bin/jason-mcp`

The live Python module was loaded from:

`/usr/local/lib/python3.12/site-packages/jason_mcp/server.py`

not directly from:

`/opt/jason-src/implementation/mcp_service/src/jason_mcp/server.py`

The pilot image contained multiple copies of the package, including source/build/install locations.

Resolution during the checkpoint:

- patch the source copy;
- syntax-check it;
- copy it into the live installed module;
- syntax-check the live module;
- restart only `jason-mcp-pilot`.

This distinction is critical for durability and rollback.

---

## Representative acceptance evidence

### Health

Public health endpoint returned HTTP 200 with:

```json
{
  "status": "ok",
  "service": "jason-mcp",
  "mode": "read-only",
  "mcp_path": "/mcp"
}
```

### Protected-resource metadata

Verified:

- canonical resource URL correct;
- authorization-server compatibility issuer correct;
- full Jason delegated scope advertised;
- bearer token via header supported.

### Authorization-server metadata

Verified:

- exact issuer match;
- real Entra authorization endpoint;
- real Entra token endpoint;
- authorization-code and refresh-token grants;
- `client_secret_post` advertised;
- `S256` advertised.

### Host protection

Unauthenticated public MCP initialize request returned HTTP 401 rather than `Invalid Host header`.

### End-to-end ChatGPT proof

ChatGPT `Jason-09092026-2` successfully answered a live operational endpoint question:

`who is logged into aot-50282`

with governed evidence identifying the last logged-in user as `AzureAD\\AlDavis` and reporting the device online.

This is the functional acceptance point for the checkpoint.

---

## Security and governance properties preserved

The following properties remain mandatory and were preserved by this design:

1. The MCP interface is read-only.
2. ChatGPT does not receive provider credentials.
3. ChatGPT does not directly invoke Datto RMM or another provider.
4. Entra authentication does not bypass Jason identity/authority.
5. Jason's Central Orchestrator remains the execution authority.
6. Only currently active read-only capabilities are dynamically executable through the generic MCP read interface.
7. Provider-wide raw discovery pages are bounded/filtered before model exposure.
8. Navigation/provider transport URLs are stripped from dynamic evidence where applicable.
9. Write tools remain disabled.
10. OAuth client secrets are not committed or documented.
11. DNS-rebinding protection remains enabled; the intended public host is explicitly allowlisted rather than disabling the protection.

---

## Durability warning — current pilot changes are not yet deployment-complete

**This is the most important outstanding operational item.**

The `jason-mcp-pilot` container is image-contained and does not bind-mount the MCP source tree. During this checkpoint, code changes were applied to both:

- `/opt/jason-src/implementation/mcp_service/src/jason_mcp/server.py`
- `/usr/local/lib/python3.12/site-packages/jason_mcp/server.py`

inside the running pilot container.

The live service imports the second path.

Therefore, the functional baseline is **proven but not yet durable across container replacement** if the current `jason-mcp:entra-pilot` image does not contain these changes.

A future container recreation from the old image can revert the MCP OAuth compatibility and transport-security fixes.

### Known backups created during the work

A host-level backup was created before the major OAuth patch at:

`/home/al/projects/jason/.mcp-pilot-backups/server.py.20260908T193905Z`

Additional container-local timestamped backups were created before later patch stages, including OAuth facade, issuer-slash, and host-allowlist changes.

Container-local backups are useful for immediate rollback but should not be treated as durable configuration management.

---

## Required durability / engineering follow-up

Before treating the MCP pilot as a durable deployable component, complete the following:

1. **Recover the final working `server.py` into the Git repository.**
   - Compare the live installed module and the working source copy.
   - Ensure the repository contains the final OAuth scope separation, compatibility issuer, authorization-server metadata, OIDC shim, and transport allowlist.

2. **Add automated tests.**
   At minimum prove:
   - protected-resource `resource` value;
   - full `scopes_supported` value;
   - exact authorization-server issuer matching;
   - `S256` metadata advertisement;
   - correct Entra authorization/token endpoint passthrough;
   - public hostname accepted;
   - unexpected hostname rejected;
   - anonymous `/mcp` remains 401;
   - valid token with `Jason.Read` is accepted;
   - missing/wrong scope is rejected;
   - expected MCP tools are present;
   - no write tools are present.

3. **Rebuild a versioned MCP image from source.**
   Do not rely on in-container mutation as the deployment mechanism.

4. **Recreate the pilot from the new image.**
   Preserve the existing secret mounts and runtime authority configuration.

5. **Repeat the external acceptance battery.**
   Verify:
   - `/healthz` = 200;
   - protected-resource metadata = correct;
   - authorization-server metadata = correct;
   - exact issuer match = true;
   - S256 = true;
   - anonymous initialize = 401 with correct resource metadata;
   - ChatGPT OAuth completes;
   - ChatGPT tool discovery succeeds;
   - `jason_mcp_status` works;
   - `discover_capabilities` works;
   - `execute_read_capability` works;
   - `who is logged into aot-50282` or an equivalent live test returns governed evidence.

6. **Preserve rollback.**
   Keep the previously working MCP image/tag available until the rebuilt image passes all acceptance checks.

7. **Only then move from pilot checkpoint to supported deployment.**

---

## Suggested operational smoke test

After any MCP image rebuild, reverse-proxy change, OAuth metadata change, Entra app change, or ChatGPT app recreation, rerun this minimum smoke test:

1. `GET https://mcp-jason.teamaot.com/healthz` -> 200.
2. `GET https://mcp-jason.teamaot.com/.well-known/oauth-protected-resource/mcp` -> expected resource, issuer, and full scope.
3. `GET https://mcp-jason.teamaot.com/.well-known/oauth-authorization-server` -> exact issuer and S256.
4. Unauthenticated `POST /mcp initialize` -> 401 with `resource_metadata` pointer.
5. ChatGPT sign-in through Entra -> succeeds.
6. ChatGPT invokes `jason_mcp_status` -> read-only governed pilot confirmed.
7. ChatGPT discovers active read capabilities.
8. ChatGPT executes one harmless live read capability.
9. Confirm no provider credential or unrestricted raw provider page is returned.
10. Confirm no write tool is available.

---

## Architectural significance

This checkpoint establishes an important Jason architectural capability:

**Jason can serve multiple conversational clients without making those clients authoritative.**

Teams and ChatGPT can be different user experiences over the same core operating model:

- external identity is authenticated by the appropriate identity provider;
- Jason binds that identity to internal authority;
- capabilities, not user wording, define execution possibilities;
- the Central Orchestrator performs governed operations;
- evidence is bounded before presentation;
- clients receive answers, not provider credentials or unrestricted provider control.

The ChatGPT integration therefore extends Jason's reach without changing the fundamental trust model.

---

## Checkpoint conclusion

**Functional baseline: ACHIEVED.**

As of 2026-09-09, ChatGPT can successfully use a Microsoft Entra-authenticated, read-only MCP interface to Project Jason and obtain live governed operational evidence.

The next engineering milestone is not additional OAuth experimentation. It is **durability**: move the proven pilot changes into version-controlled source, rebuild the MCP image, recreate the pilot from that image, and rerun the acceptance battery without relying on in-container edits.
