# PMv4 Stage C — signed release ID contract reconciliation

**Status:** source-only correction; no root mutation or deployed ticket-worker cutover.

## Evidence from attempted exact release

The Owner executed the reviewed Stage C launcher from immutable candidate `5dda0b5813448fee6f38594450a2687ade0c852a` after independently confirming the installed watchdog SHA-256 matched `9d3d4a634f2b347b760da80e0dc2bb057d3b35ddcbaf88293bffd47971d0c804`. Its nonprivileged, privileged root, and watchdog preflights all passed. The Owner used their normal AOT Entra account, provided exact affirmative consent, and received `PMV4_C_OWNER=DENIED OwnerReleaseProofDenied:OWNER_RELEASE_PROOF_FIELDS_INVALID`. No signed proof was persisted, no production mutation occurred and no production cutover was performed.

Code inspection proved a deterministic defect independent of the selected Owner account: both Stage C issuer and root verifier previously requested `release_id="pmv4-c-"+candidate_sha[:16]`, while the protected root-owned and SHA-256-pinned native Owner signer (`/usr/local/lib/jason/owner_signed_release.py`, SHA-256 `f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3`) requires `release_id="release-"+candidate_sha[:16]` in its strict signed-proof schema. Both AOT Owner OIDs are explicitly allowed by the native signed Owner proof contract. Normal-account use did NOT cause the failure. Root verification was also set to expect the incorrect Stage C prefix.

## Narrow remediation

The Stage C issuer and independent root verifier now use the existing canonical signed release-ID namespace `release-<SHA[:16]>`. The immutable packet path, Stage C action, scope hash, candidate and rollback SHAs, exact-Owner authentication, approval TTL, root public-key trust, source hash, rollback controls and production freeze/hold remain unchanged. The correction does **not** alter the signer, broaden Owner eligibility, grant account authority, bypass proof validation or accept old invalid signed release IDs.

An ephemeral in-memory signing/verification preflight against the exact pinned native signer now runs in Stage C Owner `--check-only` and again **before issuing any Entra device challenge**. It verifies both allowed Owner identities with the new release-ID contract, the exact candidate/rollback/scope/manifest/freeze bindings, and a test-only Ed25519 key. No signed Owner release record, real service key, OAuth token, approval, production mutation or ticket scan is created by the synthetic check. The source-only Stage C CI now includes negative release-ID and unit proof-binding tests. The live host's read-only check against the failed packet was already verified: `PMV4_C_PINNED_SIGNER_EXACT_PROOF_PREFLIGHT=PASS`; `OWNER_PROOF_ISSUED=false`.

## Release requirement

The failed `5dda0b...` packet cannot be modified or retried. After merge and complete protected CI, rebuild the *exact* new source image, regenerate immutable scope and release packet, run nonprivileged preflight, then obtain fresh root preflight and one authenticated exact Owner approval through the local console. The root verifier independently checks the signed claim and Owner identity; production migration and two real distinct provider scans remain separate acceptance evidence. No Stage D/E approval is implied.
