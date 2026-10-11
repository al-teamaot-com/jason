# QuickBooks Sandbox Integration Runbook

## Goal

Connect Project Jason to the AOT QuickBooks Online **sandbox** using Intuit OAuth 2.0 and validate read-only governed accounting capabilities before any production authorization.

## Current Intuit configuration

Expected developer configuration:

- App: `AOT Jason`
- Environment: Development
- Scope: `com.intuit.quickbooks.accounting`
- Payments scope: disabled
- Redirect URI: `https://mcp-jason.teamaot.com/oauth/quickbooks/callback`
- Intuit Playground redirect may remain registered for developer troubleshooting.
- Sandbox API base: `https://sandbox-quickbooks.api.intuit.com`

Do not use production QuickBooks credentials or authorize the live AOT company during this runbook.

## Secret provisioning

Provision the Intuit **development** Client ID and Client Secret through the canonical provider-secret tool. Never paste the Client Secret into chat, a ticket, Git, shell history, or documentation.

Run interactively on Jason:

```bash
cd /home/al/projects/jason
sudo python3 tools/provider_secret.py create quickbooks_development
```

Use the tool's interactive prompts. Verify secret metadata/projection without printing secret values according to `docs/operations/Provider-Secret-Provisioning.md`.

The expected host AppRole projection is:

`/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/`

## OAuth state

Default protected OAuth database:

`/var/lib/jason/openclaw/quickbooks/oauth.sqlite3`

The database contains rotating provider-issued tokens and Realm ID. File mode is owner read/write only.

The same durable OAuth state must be mounted into the MCP callback edge and Jason runtime before authorization is started. Do not create independent token stores for the edge and runtime.

Deployment wiring mounts the QuickBooks development AppRole read-only at
`/run/jason-secrets/openbao/quickbooks/{role_id,secret_id}` in both the MCP edge and runtime. The runtime activation profile remains empty by default; mounting credentials alone does not activate QuickBooks read capabilities.

## Start authorization

After the exact reviewed source is deployed to the callback edge and the required OpenBao AppRole/OAuth-state mounts are present, start the sandbox authorization flow from an authorized operator shell:

```bash
PYTHONPATH=implementation \
  .venv/bin/python tools/quickbooks_oauth.py start
```

Open the printed Intuit authorization URL and select only the intended sandbox company.

The printed URL may contain the public Client ID and one-time OAuth state. It must never contain the Client Secret or refresh token.

Intuit redirects to:

`https://mcp-jason.teamaot.com/oauth/quickbooks/callback`

A successful callback returns only non-secret connection status.

## Verify OAuth state

```bash
PYTHONPATH=implementation \
  .venv/bin/python tools/quickbooks_oauth.py status
```

Expected evidence includes:

- provider = quickbooks;
- environment = sandbox;
- realm_bound = true;
- has_refresh_token = true;
- secret_values_printed = false.

Do not print token values.

## Activate governed sandbox reads

Activation is an explicit runtime trust decision:

`JASON_QUICKBOOKS_READ_PROFILE=quickbooks-sandbox-read-v1`

Before changing this environment value, verify:

- exact source commit approved for pilot;
- provider-secret AppRole mounted read-only;
- QuickBooks OAuth DB mounted at the expected durable path;
- rollback image/container identity captured;
- current non-QuickBooks provider profile preserved.

## Harmless validation sequence

Use governed reads only:

1. `accounting.company.read`
2. `accounting.account.search` with a small bounded result count
3. `accounting.vendor.search`
4. `accounting.customer.search`
5. `accounting.invoice.search`
6. `accounting.bill.search`
7. `accounting.report.profitloss.read`
8. `accounting.report.balancesheet.read`

Confirm every call resolves through Central Orchestrator and provider `quickbooks`, and that returned company identity matches the authorized sandbox.

No general write API test is authorized by this runbook.

### Controlled sandbox mutation probe

A dormant connector-only mutation probe exists for `quickbooks.customer.create`. It is intentionally **not** registered as a live Jason governed capability. The connector enforces all of the following before sending the request:

- organization must be `aot`;
- invocation mode must be `execute`;
- active connector environment must be `sandbox`;
- production profile use is rejected before secret resolution;
- callers cannot submit raw QuickBooks JSON payloads;
- only bounded customer fields are accepted and converted server-side.

This probe is for sandbox acceptance evidence only. Promoting any QuickBooks mutation into Jason's live capability registry requires a separate governed action catalog, explicit approval policy, result projection, readback verification, and production activation review.

## Production gate

Do not connect AOT's live QuickBooks company until all of the following are complete:

1. sandbox acceptance evidence is recorded;
2. Intuit production assessment/compliance requirements are completed accurately;
3. separate Intuit production Client ID/Secret are issued;
4. production redirect/app URLs and required policy pages are configured;
5. production secrets use a separate OpenBao path from development;
6. Jason adds a separate explicit production activation profile;
7. requester authorization and financial-data handling are reviewed;
8. rollback/disconnect/revocation procedure is proven;
9. production pilot receives explicit approval.

Production is not enabled by changing the sandbox environment string.
