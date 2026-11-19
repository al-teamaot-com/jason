# Jason SharePoint Site Access — independent Grafana control

Not deployed. Install only as an **isolated** SharePoint release, after existing
PMv4, services/bundles and playbook baseline verification and Owner exact-SHA
approval. Grafana must enable `[dataproxy] send_user_header = true`
(`GF_DATAPROXY_SEND_USER_HEADER=true`), thereby supplying the authenticated
Grafana login as `X-Grafana-User`; anonymous Grafana users are denied.
Provider-side control service independently requires the server-injected bearer
credential, an Owner allowlist and a governed exact action.

`JASON_SHAREPOINT_CONTROL_AUTH_HEADER` is populated at installation time from
the approved provider-secret mechanism and contains `Bearer <redacted>`.
The same secret, never echoed, is mounted into the independent control service
as `JASON_SHAREPOINT_GRAFANA_TOKEN_FILE`. Never commit secret content.
The control service is reachable only inside the observability Docker network,
not published on the host. Grafana is not permitted to choose a user identity
or arbitrary tenant through any request body.

Provision the datasource and dashboard with Grafana's approved provisioning
process or authenticated API, with dashboard UID
`jason-sharepoint-site-access`. Confirm the dynamic site listing, owner-denied
and owner-allowed paths, and an on/off round-trip with database readback.
The supported operations are:
- `GET /sharepoint-control/sites`: signed datasource-proxied owner list and last scan
- `POST /sharepoint-control/site-access`: one exact site ID, desired bool,
  expected revision and reason; server verifies Owner, policy and readback
- `GET /healthz`: same authentication; no unauthenticated service inventory

Only source has been prepared here. There is no permission for production
Graph modifications, site writes or bypass of document sensitivity policy.
