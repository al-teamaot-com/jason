# Datto RMM First Live Read Host Proof — 2026-08-09

## Purpose

Record the first successful governed live Datto RMM read from the Jason host without retaining provider credentials, bearer tokens, or raw provider response bodies.

## Proven Boundary

- Provider: `datto_rmm`
- Logical secret: `datto_rmm.readonly`
- Runtime secret authentication: provider-specific OpenBao AppRole through JKD-003
- Capability: `datto_rmm.device.search`
- Mode: `observe`
- Provider operation: GET-only device search
- Maximum records requested: 1
- OAuth bearer token: acquired at runtime only and not persisted
- Raw provider payload: not printed and not persisted
- Connector audit events observed: `connector.requested`, `connector.completed`

## Host Result

The controlled host proof completed successfully with:

- `status=pass`
- `network_contacted=true`
- `provider_credentials_used=true`
- `access_token_persisted=false`
- `maximum_records=1`
- `collection_counts.devices=1`
- response top-level keys limited to the observed shape: `devices`, `pageDetails`
- `raw_provider_payload_printed=false`
- `raw_provider_payload_persisted=false`

This evidence intentionally records only sanitized outcome metadata. No Datto RMM device record, API URL, API key, API secret, bearer token, or raw response body is stored here.

## Security and Governance Conclusions

1. The canonical `datto_rmm.readonly` secret resolves successfully through the JKD-003 OpenBao AppRole boundary.
2. The provider-specific AppRole remains least privilege: read the DRMM secret and revoke its own short-lived runtime token.
3. The Datto OAuth exchange succeeds using the durable API credentials while keeping the bearer token runtime-only.
4. The registered Jason connector capability executes a bounded, read-only provider request.
5. The first live proof remained inside the Central-Orchestrator/provider capability architecture and did not rely on an ad hoc provider bypass.
6. Connector audit events were emitted for requested and completed execution.
7. No provider credential or raw provider object entered Git, chat evidence, ordinary logs, or this record.

## Related Changes

- PR #96 — canonical AppRole production secret invariant and documentation hardening.
- PR #97 — CAS-aware OpenBao KV-v2 provider secret writes.
- PR #98 — provider AppRole self-revoke permission.
- PR #99 — first bounded Datto RMM live-read path.

## Next DRMM Work

- expand normalized Datto RMM reads only through registered capabilities and governed resource queries;
- preserve bounded pagination and client/organization scope;
- validate response normalization against live provider shapes without persisting raw payloads;
- update/retire draft PR #77 as its Datto portions are absorbed into current `main`;
- provision and validate IT Glue independently before enabling cross-provider convergence evidence.
