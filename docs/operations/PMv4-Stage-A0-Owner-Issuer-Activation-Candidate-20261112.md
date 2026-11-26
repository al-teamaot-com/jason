# PMv4 Stage A0 — Owner issuer activation candidate (SOURCE ONLY)

**Preparation date:** 2026-11-12. **Status:** Draft / not an approved production release.

## Exact purpose and independence

The only functional change in this activation candidate is to change the
existing protected source profile
`config/pmv4-stage-a0-issuer-activation.json` from
`"mode": "off"` to `"mode": "on"`. This profile is parsed by Jason's
**existing** governed MCP deployment flow. The code and tests for this
Owner issuer were already source-promoted in PR #2448.

No production process, code, environment variable, Docker container,
root file, production freeze/hold, issuer signing key or provider state
is modified by preparing this branch. **Do not automatically promote or
merge this draft source merely to avoid a later Owner confirmation.**

## Existing production prerequisites verified

A separate, authenticated Owner-approved native production release
`release-d1b8c196dadd4b67` installed reviewed PMv4 native root
helper and existing root release reconciler, each byte-identical with
current protected source. The immutable candidate root source under
`/opt/jason/releases/d1b8c196dadd4b672ec8ba47075f27bb61c98d63`
has 13 reviewed root-owned, non-world-writable, digest-matching modules.
The signed-owner private key is mounted read-only at
`/run/jason-secrets/owner-release/private_key`, without accessing key
contents. The current MCP image is
`sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`.
Live `JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false` remains OFF. Production
freeze digest is `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`,
promotion hold digest is `11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0`,
and root breaker was CLOSED after the separate release.

The Owner previously ran `sudo stat` and observed `/etc/jason` as
root:root mode 0700 with `/etc/jason/pmv4-shadow` absent. This is
Owner-supplied evidence prior to the independent production release,
**not** an immutable native-root readback. The actual Stage A0 installer
must check all target paths under its protected root transaction.

## Controlled authorization stages

1. **Source-only promotion of this exact issuer ON candidate:** separately
   approve its final candidate SHA and reviewed source-scope SHA-256.
   The source merge is not a deployment, service restart or standing grant.
2. **MCP issuer activation release:** create and independently review an
   immutable candidate MCP image with its exact digest, source release SHA,
   previous running-image rollback digest and deployment/rollback
   contract. Require a separate authenticated Owner exact-action approval,
   including explicit permission for the MCP container replacement.
   Keep production freeze/hold controls and native release transaction
   guarantees intact. The original rollback image forces issuer OFF.
3. **Actual Stage A0 create-only root install:** separately verify the
   final protected main SHA, regenerate canonical Stage A0 scope and
   Owner manifest, and collect an exact one-use signed Owner authorization.
   The native root worker must independently check signer, root source,
   closed breaker, current LKG, freeze, protected path absence and shared
   release lock before creating the reviewed objects. The empty-baseline
   rollback SHA remains forty zeroes.

The issuer itself must refuse unverified Entra Owner identity,
short-lived or replayed authorization, stale scope/manifest/freeze
binding and any unavailable signing trust. Neither source promotion
nor issuer activation is permission for ticket-worker cutover, Runbook
Management activation, provider writes, reboots or PMv3 retirement.

## Review and acceptance conditions

The reviewed activation diff is intentionally small: one source
profile, a test of the intentional ON source under the existing
trusted-signature/rollback guard, and this operational acceptance
document. Required GitHub CI and owner-signature regressions must pass
against the exact final PR SHA. Compute a fresh immutable source
scope and candidate MCP image only after merge, and never reuse an
earlier SHA or approval.
