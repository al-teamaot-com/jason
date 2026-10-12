# Reusable governed SharePoint reader (development)

This increment adds a dedicated `microsoft_graph_sharepoint` OpenBao provider profile and a bounded Graph SharePoint transport, for reuse by Jason document intake, reconciliation, procurement, and documentation investigations. It does **not** activate any production read capability or bypass the Central Orchestrator.

## Identity and secrets

- AOT tenant: `f7054323-d52b-4863-8c2f-1898f0b6077c`
- Dedicated application: `c5692fec-3f78-44db-9a15-59c3e3bcac58` (registration display name currently includes Accounting, but the capability itself is generic)
- Graph application role: `Sites.Read.All`; no runtime write permission.
- Public certificate already registered in Entra (verified by matching certificate bytes), expires 2027-10-12.
- New OpenBao logical secret `microsoft_graph.sharepoint_read`, isolated at `secret/data/connectors/microsoft-graph/production/sharepoint-read`.
- Only approved certificate fields: `private_key_pem`, `certificate_pem`, `certificate_thumbprint`, `generation`.
- Provision only after review and deployment with the canonical `tools/provider_secret.py create microsoft_graph_sharepoint`; **do not** reuse directory/mail AppRoles or print any private key. Staged private key stays root-restricted until verified import, then retire safely.

## Integration contract

`MicrosoftGraphSharePointReader` provides bounded library enumeration, folder contents, item metadata, and byte-limited content retrieval through the injected token provider and transport. The adapter only constructs canonical Microsoft Graph GET paths; no caller-selected URL, bearer token, or method is exposed.

**Not yet production-ready:** a governed adapter must resolve Jason's authenticated identity to a validated tenant/client boundary, establish exact site/library/item authorization and information-release policy, wire the OpenBao profile and `sharepoint-read` permission profile to application-only MSAL, register reusable `knowledge.document.*` capabilities, enforce per-item sensitivity and redaction, and complete signed-off regression/integration tests. Transport is intentionally not publicly callable until these gates are met. Do not claim financial statement access from a successful Graph permission grant alone.

## Focused validation

`PYTHONPATH=implementation /home/al/projects/jason/.venv/bin/python -m pytest -q implementation/connectors/microsoft_graph/test_sharepoint_reader.py tools/tests/test_provider_secret_provision.py`

`python3 tools/provider_secret.py create microsoft_graph_sharepoint --check-only`

## Controlled acceptance

1. Deploy the approved provider-secret contract through Jason's release path.
2. Import the exact certificate into OpenBao via the canonical provider lifecycle and verify metadata only.
3. Confirm validated AOT client-to-tenant/app boundary and audit/release controls.
4. Register and discover read-only capabilities through Jason MCP, with no alternate provider connector bypass.
5. Read a nonsensitive test document from AOT Accounting Documents, verify identity/version/hash/audit, and deny a forbidden identity/site.
6. Reuse the same reader from a second approved AOT workflow, without adding another provider-specific implementation.
