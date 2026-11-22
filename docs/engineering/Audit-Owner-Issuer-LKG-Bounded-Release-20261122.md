# Project Jason — One-tool Owner signer from production LKG (source only)

This source integration **does not deploy** the archive or any MCP image.

## Exact reviewed narrow source candidate

- Parent production last-known-good Git commit: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- One-parent, reviewed MCP-only change: `1bb2fe561b1189b3c46363a84ecf3eaaa39f5877`.
- Original production MCP image rollback: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`.
- Locally built candidate image: `sha256:9b88cd5b6e2f11e378bae4b2bb0afc8c4090eb08ba401482147fd94ceb8a5425`.
- Candidate scope: only `implementation/mcp_service/src/jason_mcp/server.py` (+48 lines), `audit_journal_adoption_approval.py` (+200), its focused tests and the Dockerfile for exact original LKG base. No unrelated runtime, Ticket Core, provider, Datto, policy, agent, freeze, service identity or persistent systemd changes.
- Candidate image tested no-network/read-only/capability-less: original **37** MCP tools unchanged, exactly one additive `approve_audit_journal_adoption`, registered but **disabled by default**. Source-only regression: 40 focused pass.
- Exact new tool requires the actual licensed Owner's Entra OAuth bearer claims and a Root-produced one-use 10-minute audit offer. It signs the same exact Root stage/scope/manifest/freeze/rollback with the existing MCP service Ed25519 issuer, does not start a release, and never uses a terminal device-code login.

## Why the integration merge retains Main

The current Main source **already contains** the reviewed audit signer. A normal Git three-way merge of the narrow LKG descendant and recent Main introduced a duplicate function because both branches added the same reviewed tool at different insertion points. The integration merge preserves Main's **single existing registration** byte for byte, while including the actual bounded LKG descendant in the Git ancestry and retaining only this source-only provenance/Dockerfile as a Main tree change. All protected checks must pass on the resulting merged source, with no duplicate tool.

This makes an independently reviewed old-LKG software image distinguishable from the months of unrelated Main development. It does **not** grant the image production promotion. Before any production MCP switch, the host's original protected last-known-good `mcp_image_id` must be updated by a **separately governed, Owner-signed, one-transaction release** which verifies the candidate image, exact rollback, original freeze, health, and provider/Ticket Core readback. The existing `jason-mcp-pilot` container is NOT to be replaced by a direct `docker run` or bypass of the release controller.

## Remaining exact archive dependencies

The temporary audit watcher previously triggered independent Root drift and was safely retired. It may not be re-enabled without prior Root policy declaration. The Root worker remains installed but its policy/source SHA was pinned to the earlier Main `d189663e...`; new Root admission needs a separately approved SHA-pinned refresh or a legitimate one-shot Root invocation, never an undeclared service. Before staging a one-use Owner offer, verify the *live* signer is registered and enabled. Root stage must be signed inside 10 minutes; signed Owner evidence is independently verified by the installed Root trust and consumed once. The existing 45+ GB SQLite database may only be reclaimed after end-to-end preservation, full health, cold restore, daily timer and rollback verification.

**No success claim**: the source integration and candidate image are not production deployment, and the historical global production freeze stays active.
