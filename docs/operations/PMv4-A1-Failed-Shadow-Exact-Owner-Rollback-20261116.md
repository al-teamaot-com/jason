# PMv4 A1 failed shadow release: recover the original exact Owner transaction

**Status:** SOURCE-ONLY recovery implementation and tests, not root journal reconciled.

## Live incident — November 16, 2026

The Owner authenticated and expressly approved the isolated original A1
shadow release via Entra, exact approval
`owner-mcp-319c697027a146beac98818e5305a971`.
Its privileged preflight succeeded, then reported
`A1_ROOT=DENIED HostGateDenied:PMV4_HOST_TRANSACTION_UNAVAILABLE`.

The denial was NOT a no-op. Root installation staged source, an approved
manifest, the shadow-only gateway token and the original signed decision.
The independent shadow controller wrote
`/var/lib/jason/pmv4-shadow/receipts/owner-owner-mcp-319c697027a146beac98818e5305a971.json`
(mode 0600 root) and switched the shadow-only pointer. On error, the pointer
returned to the original `releases/0000000000000000000000000000000000000000`
empty baseline but the shadow Docker container remained running. Do not
rerun the A1 installer or repeat the already used Owner approval.

Independently inspected the isolated shadow: image ID
`sha256:779bf783c83cdefad82e34ac99335e2a2c017d8aa5588edb0ed2844a885aa9ed`,
exact Docker Compose project/service and A1 source labels, network mode none,
read-only container and no provider credentials. The container used
approximately 511.9 MiB / 512 MiB and 60 of its 64 permitted PIDs. Health
checks timed out and a Node worker hit `uv_thread_create` assertion. Its
isolation and security limits prevented healthy startup under this profile.
Do NOT claim the shadow gateway was operational.

After independent source/image/Compose-label and one-container-only checks,
the exact failed isolated Compose project was brought down, without
`--volumes`. The shadow runtime is absent; the preexisting Ticket Core and
MCP remained running/healthy; the production freeze and hold SHA256 remain
unchanged. The original root-owned pending receipt and root staging remain,
so the release is **not yet formally reconciled**.

## Reconcile original Owner-signed recovery, no new approval

`tools/pmv4_a1_pending_exact_recovery.py` is a narrow root-only one-use
rollback executor, not a release/approval endpoint. Its exact trust contracts:

1. Must be a root-owned 0400 file inside a new root-owned 0700 one-shot
   `/run/jason-pmv4-a1-reconcile-8c20` staging directory.
2. Must attest the original root-only A1 executable exactly matches the
   hash bound by the original release packet
   `ea259a6a281d3a04d16e7fe4a8fe7b90a00b78e02fe0c9dbecdadd5ccc1c9e1b`.
   Existing root-trusted A0 source modules are reused without rewriting them.
3. Must verify the original Owner's two signed parent+child proofs against
   the existing pinned Ed25519 public key, at the actual original native
   journal start time, including identical Owner OID, principal, approval ID,
   issued/expiry and exact original release/source/scope/rollback/freeze
   hashes. Do not reissue an Owner proof or treat expiry as new permission.
4. Must verify the root hash-chained A1 transaction audit's first `begin`
   matches the original single Owner approval and its exact scope, and that
   no `committed` event exists; exactly one native
   `state=started` receipt from that approval, with original candidate,
   rollback, manifest and freeze hashes.
5. Must require shadow runtime ABSENT, original empty shadow pointer, original
   production LKG/freeze/hold intact, independent breaker+drift PASS, fresh
   Ticket Core health and two native release leases. Docker 29's exact
   lowercase absent-object diagnostic is normalized by the previously
   reviewed A1-only trusted adapter, never by modifying the A0 native helper.
6. Call the native `ShadowController.reconcile_pending_rollback()`,
   which takes both host locks and its own existing shadow release lock,
   checks original zero baseline, verifies absent shadow + live Ticket Core,
   and atomically marks the original receipt `rolled_back`.
7. **After** native receipt rollback, remove only the original root audit's
   originally created exact source files using the source-side inode/hash
   checked cleanup; leave the root transaction journal/receipt as immutable
   evidence. Append an audited original-owner recovery event.
8. Fail closed on mismatched owner, stale/untrusted source, foreign files,
   anomalous receipt, unknown container, changed production controls or
   any unauthorized new service.

The local launcher
`bash tools/pmv4_a1_recover_existing_owner_local.sh --check-only`
does all available source tests and non-mutating checks. Its `--recover`
requires only a real local sudo TTY to inspect protected root-only evidence
and complete the **previously authorized rollback**; it does **not** open
an Entra sign-in flow or request a second Owner exact-action approval.

The existing origin controls remain unchanged. Reusing the prior approval
is limited to rollback; a future *new* release candidate may eventually
require distinct fresh exact-action authorization, but **only after** the
shadow resource configuration is independently corrected and tested.
Avoid another incomplete installation and additional needless approval
ceremonies.

## Separate engineering defect for future release

`host_release_transaction()` currently catches arbitrary `OSError`
thrown **inside** its protected `yield` body and translates that to
`PMV4_HOST_TRANSACTION_UNAVAILABLE`. This can mask the true underlying
Docker/filesystem/recovery error and cause needless approval retries. It
must be corrected in a separately tested source release to catch lock
acquisition failures without replacing errors raised by the deployment
itself.

A1 current immutable Compose `mem_limit: 512m`,
`pids_limit: 64`, `cpus: 0.5` does not pass actual OpenClaw gateway
health acceptance. A bounded, separately reviewed change to the isolated
gateway resource profile and health test is needed. It must not weaken
`network_mode: none`, read-only filesystem, non-root user, dropped caps,
no-new-privileges or production Ticket Core isolation.

**Remaining proof:** native root receipt state `rolled_back` and audited
source cleanup. This recovery is not complete until the root postflight
confirms original empty baseline, no container, absent installed source
objects and healthy Ticket Core under protected freeze/hold.
