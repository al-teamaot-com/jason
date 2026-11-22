# Jason root policy — one approved financial container allowance

**Source status:** source-only until reviewed source commit, protected CI,
independent exact Entra Owner consent and SHA-pinned, isolated root execution.
No production policy, unit, service or container has been changed by this source.

## Why the separate policy action is necessary

The independent financial organizer release (source
`c205bb4ac163e7d433796f2f4839a90c7cc1f56b`, OCI image
`sha256:913322f47c96ae56f5ae9bb4c6e742ebe36691dc28ca56c202b124bf969ea195`)
has passed its immutable image, dedicated AOT accounting SharePoint AppRole,
scoped read-only tenant/drive/21-child intake and protected CI preflight.

The installed native drift watchdog uses the **root-owned effective** policy
`/etc/jason/release-readback-recovery/production-desired-state.json`
through `jason-production-drift-watchdog.service.d/10-readback-recovery.conf`.
The immutable LKG source policy `/opt/jason/current/config/production-desired-state.json`
is **not modified**. It does not permit the new
`jason-financial-statements` container. Promoting it without an approved
effective-policy allowance would reopen the protected breaker.

At 15:32 EST, the four catalog recovery systemd units were installed by a
separate Owner-approved catalog transaction but absent from the root effective
policy. PR #2553 merged the **separate**, exact four-unit root-policy repair,
source `7792e9018cc4535d0517dff4bf29e35644f5e9e4` with Owner package
already staged under
`/srv/jason/archive/engineering-artifacts/pmv4-catalog-drift-7792e9018cc4535d0517dff4bf29e35644f5e9e4`.
That action **must run and be accepted** before this one. Removing catalog
recovery timers instead is explicitly not part of this change.

## Single permitted financial policy delta

After the signed PMv4 catalog four-unit repair, the exact root-owned effective
policy must have SHA256
`e17ffed6b6c4589721d69a46a25b80f80d571e8b67e1726c881647d07e29a2b8`.
The only reviewed transformation is
`allowed_running_containers += ["jason-financial-statements"]` with
duplicate-free sorting and unchanged **every other key/value**. Resulting
canonical JSON file SHA256 is
`cf8aa933c78513b1b3b4391c68d71a04a17f5d3fa47e6c7d14d96347ce0b2647`.

`tools/financial_container_policy_reconcile_root.py` requires:
- Separate 15-minute, one-use, cryptographically verified Entra Owner proof
  bound to exact reviewed source SHA, these exact SHA256s, scope and unchanged
  production freeze. The existing pinned root public key verifies the proof
  before a production file is opened for writing.
- Root-owned PMv4 accepted reconciliation receipt bound to the exact four-unit
  target SHA, genuine native breaker **CLOSED**, fresh drift PASS, preserved
  frozen production source `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`,
  and all five protected runtime/MCP/PMv4/Teams/OpenBao running.
- Existing OCI image ID and source-revision label exactly match the reviewed
  financial candidate. No financial container is already installed.
- Both native production and PMv4 release locks held exclusively. New, root-only
  one-use audit receipt + exact previous-policy byte backup written before the
  root policy is atomically replaced.
- After releasing the locks, **two fresh native drift watchdog PASS results**,
  exact new root policy file readback, protected container ID/image/start-time
  invariance and unchanged freeze. A failure restores the exact old policy bytes
  under the native lock (if not concurrently changed), records failure and
  fails closed; the old release freeze remains untouched.

This root policy allowance **does not start a new container**, grant approval
for financial SharePoint moves, change runtime/MCP images or reopen the freeze.
The independently reviewed financial component release requires its own
**separate Owner proof** via native installed controller; it runs only after
successful root policy and clean native health.

## Acceptance

1. Source protected CI all PASS; exact source and manifest staged immutable.
2. Separate PMv4 four catalog-unit policy repair actual Owner authentication,
   immutable root receipt, watchdog PASS, native breaker revalidation.
3. This policy exact-action Owner authentication and isolated root execution:
   signed proof + root receipt, exact only-container allowance, two fresh
   watchdog passes, freeze and protected services unchanged.
4. Separately Owner-authenticated financial component promotion through
   already installed native controller, single Compose service running from
   immutable image; watchdog remains clean and breaker closed.
5. Tomorrow's real 05:00 America/New_York live SharePoint discovery/write
   receipts, idempotency and duplicate/ambiguity safety evidence. Do not
   report whole-task completion from a staged image or a running container.
