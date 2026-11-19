# Establish the Jason SharePoint client boundary

This is a configuration-only operation. It verifies the dedicated certificate
from OpenBao by acquiring an application token, checks the token's tenant,
application, service-principal and `Sites.Read.All` claims, then performs a
bounded app-only site enumeration. It records only a validated boundary after
the Graph check succeeds. It does not use a delegated user token, change Entra
consent, read document content, grant a site, deploy containers, or restart a
service.

Run from the clean release worktree as the authenticated AOT operator with
`sudo -i`. Provide these non-secret settings in the operator environment:

- `JASON_SHAREPOINT_AOT_TENANT_ID`: Entra directory ID.
- `JASON_SHAREPOINT_APPLICATION_ID`: dedicated SharePoint app client ID.
- `JASON_SHAREPOINT_SERVICE_PRINCIPAL_ID`: its Enterprise Application object ID.
- `JASON_SHAREPOINT_EXPECTED_CERT_THUMBPRINT`: registered public certificate thumbprint.
- `JASON_SHAREPOINT_AOT_DOMAIN`: `teamaot.com`.
- `JASON_SHAREPOINT_AOT_HOSTNAMES`: `absolnet.sharepoint.com`.
- `JASON_OPENBAO_URL`: local OpenBao URL.
- `JASON_SHAREPOINT_OPENBAO_ROLE_ID_PATH` and
  `JASON_SHAREPOINT_OPENBAO_SECRET_ID_PATH`: dedicated AppRole files.

First run the read-only preflight:

```bash
clear
cd /home/al/jason-worktrees/<verified-release-worktree>
python3 tools/sharepoint_boundary_bootstrap.py --expected-sha <exact-reviewed-sha>
```

The only success result is `status=preflight_pass`; it reports the number of
sites seen, never their names or contents. A failed token claim, certificate
check, Graph enumeration, host check or source check leaves the durable
boundary unchanged.

After exact Owner approval for the boundary-only action, run the same command
with `--apply --approval-reference aot-sharepoint-client-boundary-create-only`.
It requires a clean exact-SHA worktree, a locally authenticated `sudo` session
from `al`, healthy unchanged Jason runtime/MCP containers and a root-owned
boundary database with private permissions. It writes an append-only root-only
audit event under `/var/lib/jason/independent-component-release` and uses Jason's
signed onboarding and SQLite boundary services.
The operation is idempotent for the same already-validated binding.

Boundary creation alone does not activate the reader, install the isolated
Grafana sidecar, enable the Grafana user header or start daily discovery. Those
remain separately controlled release steps.
