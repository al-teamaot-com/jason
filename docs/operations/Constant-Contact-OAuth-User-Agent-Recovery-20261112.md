# Constant Contact OAuth client identification repair

Source-only hotfix based on live production LKG d1b8c196dadd4b672ec8ba47075f27bb61c98d63.

## Verified incident

After approved same-image MCP credential projection, the callback resolved its OpenBao AppRole and valid 32-byte encryption key and accessed the shared mode-0600 OAuth database. No token is stored; pending state was consumed. The live callback intentionally redacts its failure, so the original upstream POST response cannot be reconstructed from its logs.

Independent unauthenticated GETs from the same MCP network to the documented OAuth issuer token endpoint return HTTP 403, Cloudflare error 1010, using urllib client identification. Public issuer comparison with the truthful Jason/1.0 (+https://teamaot.com) User-Agent passes this edge rejection. This proves an issuer interoperability defect; successful authorization-code exchange is still unverified. No authorization code was replayed, token printed, contact imported, credential changed or live source modified during diagnosis.

## Minimal correction

Add one explicit truthful User-Agent header in the existing shared OAuth token request function. Both initial exchange and refresh use it. Preserve the exact issuer, TLS verification, client authentication, scopes, expiry validation, one-time state and encrypted storage. No browser impersonation, challenge automation, permission increase or provider-write activation.

Regression checks emulate the observed edge rejection for missing client identification, for both code and refresh grants. They fail before the patch and pass afterward. Run all Constant Contact connector tests and focused runtime/orchestrator acceptance before release; exact GitHub CI is required.

## Release boundary

This branch is anchored at the running LKG to keep an exact narrow release candidate reachable after an ordinary reviewed merge into main while preserving all newer main changes. Compare full candidate-to-production scope before release; do not deploy moving latest main or unrelated PMv4 activation. Classify conservatively under the authentication release rules. Preserve both newly approved read-only Constant Contact AppRole mounts, shared OAuth storage and the Owner signer in the native candidate. If native preparation cannot preserve those projections, stop for a reviewed release configuration; do not patch a running container.

Exact source promotion approval, native build/preproduction, independently verified rollback and production Owner approval remain required. Only after verified deployment, issue a fresh OAuth URL, obtain real AOT consent and confirm encrypted tokens through the canonical status CLI. The failed state cannot be replayed. Account/list binding, consent-backed import/readback and scheduler remain separate acceptance gates. No release approval is implied by this document or PR.
