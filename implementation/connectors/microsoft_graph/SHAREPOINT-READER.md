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

## October 12 integration update

The branch now includes the reusable GovernedSharePointConnector with four internal operations: knowledge.library.search, knowledge.document.search, knowledge.document.metadata.read and knowledge.document.content.read. This **adapter exists in source but is not yet wired to live identity-boundary, policy, credential or capability registration services**, so no new production read was activated.

Reconciled security checks from draft PR #1120: exact Graph drive membership under each authorized site; item parentReference drive ID; fail-closed unsupported Graph pagination; verified file size before content read; strict GET only; refusal of caller-provided tenant, bearer token or arbitrary endpoint selectors. The injected authorizer must independently approve each caller/client/tenant/site/drive/item operation before Graph access.

Document-content responses are base64 and SHA256 within the bounded internal adapter. Registering a public content-read MCP capability requires separate evidence-release limits and sensitivity classification. Production-wide application Sites.Read.All must not be interpreted as permission for every Jason user to view all AOT documents.

Focused unit tests exercise negative requester/client binding, unauthorized site, path injection, mismatched drive and file identity, oversized content and missing information-release authorization. CI is defined in .github/workflows/sharepoint-reader.yml.

## Separate runtime composition

The inactive MicrosoftSharePointRuntime builder in implementation/runtime_service/src/jason_runtime/microsoft_sharepoint.py uses the existing MSAL certificate and OpenBao resolvers, but with isolated provider microsoft_graph_sharepoint, secret microsoft_graph.sharepoint_read and profile sharepoint-read. It neither acquires credentials nor contacts Microsoft during construction. Production requires a separately validated boundary record and deployment approval.

## Unregistered provider-neutral capability catalog

The build_sharepoint_read_manifest factory declares the four reusable read-only library/document operations under the canonical Microsoft Graph provider. This manifest is deliberately **not registered into the active orchestrator or MCP catalog** while information-release and complete live provider acceptance remain outstanding.

## October 30 integration-gate review: PRs #2125 and #2128

The required repository-hygiene gate found that #2125 and #2128 also modify `implementation/connectors/core/openbao_secrets.py`. Their inspected patches add distinct `it_glue.readwrite` and `microsoft_graph.user_create` secret paths and field allowlists; this SharePoint PR adds only `microsoft_graph.sharepoint_read` keys and a separately scoped certificate secret. The changes are additive and conceptually compatible, but both overlapping workstreams must survive later integration and receive full secret lifecycle regression tests. **Integration coordination: #2125, #2128** is declared in this PR body. No live secret provisioning, credential values or production approval is implied.

## AOT-only validated SharePoint service binding gate — October 30

## AOT-only validated SharePoint service binding gate — October 30

\`require_validated_sharepoint_service_boundary\` now verifies a **separate** active Kernel \`microsoft_graph_sharepoint\` tenant binding with \`profile=sharepoint-read\`, expected AOT client ID \`client-aot-internal\`, domain \`teamaot.com\`, a validated Entra service principal, and a validation timestamp. A mail or directory-read boundary is not a substitute. The KFS runtime calls this guard before making its approved document-reader available, and rechecks it on every cached document-identity lookup. Tests deny wrong tenant, cross-client, revoked, pending, wrong profile, no service principal and absent validation.

**Current host evidence (read-only):** AOT's Microsoft directory and mail boundaries are validated, but no separate \`microsoft_graph_sharepoint\` profile is present in the live boundary database. The canonical provider-secret \`--check-only\` contract passes. This remote user cannot inspect the root-protected AppRole staging directory (normal \`stat\` permission denied; \`sudo -n\` requires a password). Therefore **do not claim the AppRole credentials are absent** from this inspection; a privileged metadata check and exact AppRole verification are still required. The dedicated Entra registration and certificate listed above were previously documented but not independently revalidated in this session.

### Privileged controlled-release prerequisites

The owner has approved **read-only use of existing AOT SharePoint copier logs and delivery receipts** (#2176). This approval does not grant broader permissions or deploy code.

- Validate the existing dedicated SharePoint Entra app, read grant, certificate and tenant binding without revealing credential values.
- Use the canonical \`tools/provider_secret.py create microsoft_graph_sharepoint\` lifecycle **only under approved privileged release control**, not with a copied directory/mail AppRole.
- Create and validate the dedicated \`microsoft_graph_sharepoint\` \`sharepoint-read\` Kernel client boundary via the canonical onboarding/identity service; do not insert a forged validated record into SQLite.
- Restrict the AOT service to exact approved Admin Documents site/drive/item grants with bounded expiry. Document manifest changes and boundary revocation must invalidate cached customer claims before the next report.
- Verify an allowed Jason-workload metadata/content read, forbidden file/tenant/client denial, version/digest audit, and failure-safe result. Then test LaToshia's exact KFS top-five question with verified customer mapping and explicit meter exceptions.

No protected-main merge, credential mutation, production container restart, or production deployment was performed in this development session. A release still requires full CI, independent review, exact candidate/rollback SHAs and final owner authorization.
