# PMv4 E: one-Owner native canary release and clean rollback

**November 18, 2026 — SOURCE ONLY. No Owner proof or production mutation.**

The engineering candidate is protected-main source
d85faad76881439953527d391c314df0f5d2967a and immutable source
packet /srv/jason/archive/engineering-artifacts/pmv4-e-canary-d85faad76881439953527d391c314df0f5d2967a.
Its candidate manifest SHA-256 is
92472001a64ecdd3d9c53d321b544aa7d10bdcf27f5dd2ad8b72b97bca6d2924
and exact scope SHA-256 is
b9107ef85af95fe20ecd40523006e561c90d06585835d63a9970719bbd03f4c6.
The reused preproduction image's actual label revision is
75f2b4c0c48a15bd17d700b9f039fe56623e3f52. It is NOT represented
as having been rebuilt from d85faad7.

The versioned root/Owner source packet includes four new components:

- tools/pmv4_e_canary_oneowner_builder.py: creates an immutable staged
  directory with only the exact reviewed Git blobs from the final
  protected-main commit (source SHA and required CI verified), owned by
  the unprivileged operator with no world/group access. It never issues
  Owner proof, invokes sudo or deploys.
- tools/pmv4_e_canary_oneowner_root.py: independent privileged root
  preflight verifies protected source/CI, exact candidate and trusted
  original generic component controller hashes, live freeze/LKG,
  closed breaker and zero native drift, root-only Stage C, D and A1
  accepted receipts, protected prior desired-state SHA, immutable
  existing OCI labels and no preexisting conflicting canary. Root
  execution requires original one-use signed Owner proof tied to the
  exact action, candidate SHA, source build SHA, manifest/scope/freeze
  and root-pinned Ed25519 public key.
- tools/pmv4_e_canary_oneowner_owner.py: uses the existing pinned AOT
  Entra OAuth verification and signed Owner issuer, not Teams or an
  impersonated provider identity. It issues one short-lived exact
  signed proof only AFTER independent privileged root preflight, on
  authenticated Owner confirmation.
- tools/pmv4_e_canary_oneowner_local.sh: one local command performs
  source preflight, privileged root preflight, one Owner authentication,
  one exact root transaction. A separate --recover path can consume
  the ORIGINAL signed proof for cleanup only, never re-promote.

The exact action is
pmv4-e-oneowner-providerfree-native-canary-and-cleanup-v1.
Typed confirmation:
APPROVE-ONE-EXACT-PMV4-E-PROVIDERFREE-CANARY-AND-CLEANUP.

## Native bounded release test

After exact root and Owner gates, root stages only the new canary
companion under the installed trusted root, leaving all existing
independent component core/financial adapter files byte-identical.
It stages the reviewed canary bundle and per-candidate verified
CI readback in the existing native component release controller.
The one-container protected policy allowance is committed only while
the canary is active. No watchdog, breaker or production freeze is
disabled or bypassed.

The unchanged generic ComponentReleaseController then consumes the
signed one-use proof, activates the private-network provider-free
canary, independently verifies effective image/memory/no ports/no
external network/no credentials, and commits a native accepted
receipt. No production Ticket Core, runtime, MCP, Teams gateway,
shadow, OpenBao, provider or PMv3 engine is restarted.

After acceptance the exact Owner-scoped transaction removes ONLY
the canary using its pinned host callbacks, proves it absent,
clears ONLY its exact native active pointer (preserving the signed
native acceptance receipt), restores the exact original protected
policy bytes, checks the protected container identities and freeze,
and writes a separate immutable root parity result. A bounded
--recover uses only the original signed proof, never a new Owner
grant, and restores an interrupted canary cleanup. If the native
rollback itself is indeterminate the protected breaker remains
native; no fake-success receipt or force-close path exists.

## Remaining boundaries

This one-shot canary is NOT PMv3 retirement, not approval for a
provider-specific SharePoint workflow, and not authorization to
disable six release/engineering controls. The genuine PMv4
engineering scheduling and watchdog/root reconciler replacements
still require exact live parity, protected desired-state unit
transition, rollback and a separately scoped authenticated Owner
retirement release. Do not call Stage E complete based only on
passing synthetic canary tests.

**Deployment state: unissued, not installed.** Root-only preflight
may still detect a changed protected desired-state fingerprint,
existing component CI conflict, or root acceptance receipt. In that
case it must deny BEFORE asking the Owner to approve.
