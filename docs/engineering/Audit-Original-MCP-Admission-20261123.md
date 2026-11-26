# Audit migration admission with the original MCP image

Status: source engineering and isolated tests; no production deployment or archive cutover.

## Concrete failure
The audit migration installer previously consulted the optional Root overlay grant before considering the actual running MCP image. An expired or superseded overlay grant therefore rejected the already-approved original MCP image, even though the optional overlay had never been deployed. This also made the existing independently authenticated Root installer depend unnecessarily on deploying the optional ChatGPT signer first.

## Bounded correction
The protected peer inventory independently inspects the exact Docker container set. When that inspection finds the original immutable MCP image digest, admission uses the existing baseline image inventory. The installer and reviewed scope use the same actual inspected image, so the exact approved scope still captures the real producer set.

Every non-baseline image still requires the existing complete Root-controlled, unexpired, candidate-bound overlay proof and exact image provenance. Missing or ambiguous MCP inventory, unknown images, changed peers, invalid overlay custody, replay, expired grants, changed scope, native drift or an open breaker remain blocking. No policy, proof or expiry is edited or renewed; no caller-provided environment or request can select an image.

## Operational sequence
1. Prepare a clean exact protected-Main checkout with owner-only source write permissions. Verify source hashes and complete applicable CI.
2. Obtain actual current full integrity/restore evidence and native health; do not clear the breaker based on stale or synthetic evidence.
3. Run the existing Root installer preflight and independently authenticate the licensed Owner for the exact archive scope. This existing CLI path does not require replacing MCP solely to install an approval issuer.
4. Execute the existing event-preserving migration, verify current event parity, historical reads, cold restore, rollback, daily rollover and actual root-disk reclamation. Preserve the production freeze and provider service identities.

The optional ChatGPT signer remains a separate deployment option; its expired trust cannot authorize a replacement MCP image. Source merge and passing tests do not constitute archive adoption.

## Regression coverage
Realistic Docker-inventory fixtures reproduce original-image rejection with expired and superseded optional trust. They then prove original-image acceptance and consistent scope generation, while an actually deployed expired overlay and unknown replacement image remain denied. Existing protected-peer, provenance, signed-Owner and migration tests continue to apply.
