# Jason Secure Credential Control — 2026-09-19

## Section Goal
Build and production-prove a secure Jason Credential Management Grafana dashboard that can add or rotate approved provider API credentials through a narrowly scoped credential-management service, validate the exact provider field contract, retain OpenBao KV rollback history, and expose only secret-safe metadata.

## Security architecture
Grafana is the control surface, not the secret store. Browser requests use Grafana's server-side datasource proxy. The datasource bearer token is held in Grafana secure datasource storage. The credential-control service authenticates separately to OpenBao using a dedicated AppRole whose ACL contains only the exact approved provider KV data/metadata paths; wildcard provider paths are prohibited. Secret updates use KV v2 compare-and-set against the current version. API secret values are never returned by the service, written to audit JSON, exported to Prometheus, embedded in dashboard JSON, or committed to Git.

The service records only timestamp, actor, provider, action, old/new KV version, status, correlation ID, and `secret_values_recorded=false`. Microsoft Graph certificate/private-key material is intentionally excluded from the initial API-key form.

## Implemented source
- `tools/credential_control_service.py` — authenticated inventory/update API, exact provider field validation, CAS writes, secret-safe audit.
- `tools/provision_credential_control.py` — one-time dedicated OpenBao policy/AppRole bootstrap with exact path ACLs and generated HTTP proxy token.
- `tools/tests/test_credential_control.py` — proves exact/no-wildcard policy, unexpected-field rejection, CAS behavior, and no secret in audit.
- `infrastructure/showcase/grafana/dashboards/jason-credential-management.json` — Business Forms dashboard for approved API-key providers.

Focused tests: 3 passed.

## Production acceptance state
Source implementation is complete. Production activation requires the one-time OpenBao administrative bootstrap because creation of the new least-privilege policy/AppRole is deliberately not possible with Jason's existing provider read/write identities. No existing provider secret, AppRole, or Grafana credential has been broadened or reused to bypass this boundary.

Section Goal status: **PARTIAL / BLOCKED ON ONE-TIME OPENBAO ADMIN BOOTSTRAP**. After bootstrap, acceptance requires service deployment, Grafana secure datasource creation, inventory proof, one controlled credential rotation/validation, proof that the prior KV version remains available, and secret-leak checks.
