# Bounded daily audit-journal migration v1

Status: **source under review; production not installed or adopted**.
Owner direction: November 21, 2026 — prepare one bounded migration and rollback.
Destination: **the existing archive drive**, as selected by the Owner.
Classification: **High-Risk**: shared journal, three consumer replacements,
Root storage custody, boot recovery and integrity-policy adoption.
Preparation baseline: a4194c9ee128e1f39938ec175fc52a4fbbd7f52d.
Related work: #1324, #1948, Owner-objective framework #2670/#2671; preparation #2672.

This is one defined storage objective. The source remains dormant until the
exact protected candidate passes complete Root preflight and the existing
independent Entra Owner verifier authorizes its immutable scope. Source tests,
a PR and source publication do not constitute production acceptance.

## Outcome and limits

Keep the active orchestration journal bounded while preserving all committed
history, event-ID uniqueness, historical lookup and execution/correlation
reconstruction. Retain the existing service identities and Root protections.
No provider business write, authority/grant change or approval-record repair
belongs to this migration.

| Item | Defined behavior |
| --- | --- |
| Canonical journal | /var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3 |
| Historical archive | /srv/jason/archive/governed-audit/orchestration |
| Daily boundary | 00:15 America/New_York, including 23/25-hour days |
| Size rollover | 1 GiB main database plus WAL |
| Admission ceiling | 2 GiB main database plus WAL |
| Reserved outcome capacity | 24 MiB per admitted execution; at most 32 in flight |
| Event envelope | 256 KiB total; each metadata field at most 512 bytes |
| Storage evaluation | Existing systemd scheduler; dedicated bounded storage timer every 60 seconds and at the daily boundary |
| Handoff | Exclusive gate at most 30 seconds; slow copies/checks run outside it |
| Final rollback delta | At most 128 MiB / 100,000 rows, within the same handoff |
| Initial execution | One claimed exact Owner objective, at most eight hours |
| Covered recovery | At most eight additional hours, with the same exact rollback scope |
| Archive retention | All history retained; no age-based archive deletion |
| Backup claim | Separate-disk archival; off-host backup is outside this scope |

These are enforced policy limits and execution budgets. Synthetic latency
measurements are not promises about a production file with millions of rows.
A budget failure preserves evidence and history and cannot be labeled accepted.

## Verified preparation evidence

Root inventory completed with no denied process entries and four open handles,
all belonging to the three expected consumers. Their installed event-store
source bytes matched. Their configured journal path and physical shared mount
were separately inspected. Root and archive storage use distinct filesystems.

A later read-only size sample covered 2,000 recent events: maximum payload
1,534 bytes and maximum metadata field 61 bytes. It exported no payloads.
The append-only high-water mark was about 32.6 million rows. These observations
support the chosen preparation approach; they do not describe every historic
payload or prove future workload limits.

Keep live container IDs, complete configurations, private source receipts,
file identities and detailed host measurements in Jason's private artifacts.
Public source contains no live audit/customer records or service credentials.

## Exact application changes

The Runtime, MCP and Ticket Core keep their **same already-running image IDs**,
commands, entrypoints, service identities, secrets, ports, volumes and network
configuration. Replacement adds three read-only source-file mounts, four
read-only profile/history mounts, a fixed journal-profile environment variable
and the journal component's source label. Static network addresses or conflicting
mounts fail planning before mutation.

Three controlled container replacements are included in the approval scope,
with up to three original-configuration recovery replacements. Availability
interruption is part of that scope. Docker itself is not restarted.

The opted-in factory selects the new reader/writer only for the fixed canonical
journal. Other paths and the legacy default remain unchanged. Every active
operation uses the protected shared handoff gate and opens its current database
connection for that operation. Closed pending connections are not retained.

Historical get, execution and correlation queries include the active journal and
all closed segments, ordered by occurrence time and event ID. Root-custodied
Bloom filters and an LRU of 32 archived handles bound lookup resources. Global
event-ID checks continue across rollover. An unavailable or changed archive
invalidates access and blocks new admission.

Already-invoked outcomes first enter bounded durable receipts **inside the same
active SQLite database**. Reconciliation promotes the original event ID and bytes
after uniqueness checks; it never invokes a provider. An old unreconciled receipt
blocks new admission and health. Completed, denied, check-only, terminated and
deduplicated paths release their reserved capacity.

## One approval through operational acceptance

1. Verify exact clean source and metadata against the immutable candidate.
   Verify protected Main CI, the migration's Main-push acceptance, live native
   protection, source schema, consumer configurations, complete Root process
   inventory, storage identity/reserves and stopped-container recovery capacity.
   All this runs before the Owner prompt.
2. Use the existing pinned Entra verifier once. Display the exact source,
   rollback, targets, disruption and scope digest and require the exact action.
   Claim that scope in a Root-only durable approval/source snapshot.
3. Install the immutable fixed-path controller, native health bundle, policy,
   persistent catalog, boot support and exact release worker. Queue the Root
   worker as an actual persistent systemd job.
4. Hold both existing cross-release transaction locks. Block new admissions,
   drain current-generation governed writes, replace the exact consumers with
   dormant compatible code and verify their loaded source. Historical unresolved
   consumed claims remain unchanged and are never interpreted as permission
   to retry a provider.
5. Under the exclusive handoff, verify no legacy handles, write and fsync the
   one-use intent, checkpoint and preserve the old source and publish a small
   active journal. Remove temporary operational triggers before historical seal.
6. Outside the handoff, fully integrity-check closed history, copy and checksum
   it, verify standalone read-only restore access and publish Root-custodied
   proof/fingerprints. Verify historical reader routing.
7. Actually reconstruct a complete legacy-compatible database on the archive
   drive, full-check its content/schema/counts and perform a cold legacy restore.
   Only then may the exact redundant local source copy be reclaimed.
8. Run an actual scheduled acceptance rollover and complete dependent seal,
   reconstruction-coverage and reclamation work in that invocation. Complete
   the existing full, fast and drift checks and original protected revalidation.
9. Confirm genuine current activity and historical reads through all three
   consumers, verify protected peers and unchanged freeze/hold/Stage E evidence,
   then record acceptance. No synthetic production event is injected as a canary.

An unknown Docker response is resolved from exact IDs, stopped before-images,
configuration and native state before retry. A lost response after stop, rename,
create or start does not authorize another blind replacement.

Source CI and other non-production engineering can run without another Owner
decision. An amended impact, expired grant or changed protected boundary requires
a revised exact objective rather than replaying an old decision.

## Root custody and boot support

The public /run/jason/audit-journal/profile.json points to persistent control at
/var/lib/jason-audit-journal/control. The catalog and lock survive reboot.
Root restores the ephemeral pointer from its adopted policy.

Seal only the **top directory metadata** of /srv/jason/archive as Root:Root 0755;
do not recursively change engineering directories. Existing Al-owned engineering
children remain usable. Historical databases and filters are Root:writer-group
0440. Public metadata/source is Root:Root 0444. Private approvals, configurations
and recovery records remain in Root-only directories.

Boot recovery runs in the Host mount namespace before Docker starts. If rollback
requires an archive-backed legacy database, it restores the descriptor-guarded
canonical file bind before containers inherit their recursive shared mount.
Root recovery cannot use a private mount namespace. Held no-follow source/target
descriptors prevent privileged symlink redirection.

The Root desired-state update declares the new storage units and exact recovery
container prefix. The accepted Stage E marker, accepted native tree and original
shared Root worker bytes remain unchanged.

The unchanged shared worker receives a separate compatibility wrapper. Generic
whole-host materialization must explicitly support the adopted data layout.
Original typed actions retain their existing authorization and safety checks.
A future incompatible whole-host recreation must not silently drop data mounts.

## Integrity and resource model

Active health uses a bounded consistent snapshot, actual full integrity and a
real restore proof. Historical proof is accepted only under protected custody,
unchanged fingerprints, the bound verifier and complete catalog coverage.
Full historical scrub becomes due at 28 days and fails health after 31 days.
A checksum alone is not a SQLite full-integrity check.

The new health implementation is installed in its own immutable bundle. Older
pinned repair sources remain byte-identical. Existing authority/replay/security,
key and delegation checks and the original 5,400-second checker deadline remain
effective. Routine maintenance requests real native checks and the original
Root revalidation; it never edits a PASS, breaker or LKG document.

Rollback reconstruction copies the already indexed historical baseline, then
appends newer segments in SQLite. A real full target proof independently checks
each source segment's ordered content hash. It does not reinsert tens of millions
of old rows through Python or pretend combined hashes are a fresh full check.

Preflight reserves three source-file equivalents plus workspace on the archive
drive and local active/WAL workspace. Per-operation gates enforce additional
reserve checks. Root-owned creation records identify disposable temporary work
and prepared copies. Recovery removes only unreferenced exact work with no open
handles; a live handoff, current recovery plan and published history are protected.

## Rollback preserving all new events

Disable rollover scheduling and stop the active maintenance service before
starting recovery. Pause new admission, reconcile pending outcomes and drain
admitted executions. While current writers still run, reconstruct and
fully verify the legacy database on the archive drive from every closed segment
and a consistent active snapshot. Bind catalog generation and snapshot watermark.

Recheck the generation, then merge only the bounded post-snapshot tail under the
handoff. Preserve the small active source and publish the archive-backed legacy
file through the canonical descriptor bind. Keep admission paused until fresh
containers with the exact original configurations inherit that mapping. Remove
the barrier, complete actual native health and protected revalidation and retain
all receipts.

Rollback restores legacy application behavior and data format with newer events
included. It retains archive custody, minimal data recovery/boot support, the
compatible health bundle/scratch directory and the declared compatibility guard.
It does not claim every filesystem setting returns byte-for-byte to its old state.
The adopted rollback desired state disables the storage timer while declaring
the retained recovery support.

An initial cutover cannot replay after its completed one-use claim. New rollback
publication requires the original exact release/recovery window; boot recovery
may finish an already-recorded intent without creating new release authority.

## Preparation tests and remaining release gates

Disposable tests cover real SQLite WAL, concurrent writers, day/size/DST rollover,
global uniqueness, missing/corrupt archives, outcome receipts, full reconstruction,
cold restore, final-tail preservation, changed-generation rejection, custody and
symlink/inode substitution, claimed-work cleanup and paused legacy publication.

The isolated Root image additionally exercises UID 1000 writes, distinct
filesystems, actual kernel file binds, recursive container mounts, reboot mapping,
one-use recovery and filesystem bootstrap interruption/rollback. It has no Host
or secret mounts, no Docker socket and no network. Three existing consumer images
also passed read-only source-mount smoke tests with synthetic data only.

Before a production command is offered, finish source review/CI, unit verification,
exact source publication and release-candidate reconciliation. The older pending
Owner-objective installation must be reconciled deliberately when material Main
changes; its old launcher cannot simply be assumed valid against a new candidate.
Install the audit layer first. The updated Owner-objective installer accepts its
policy only after Root-owned consent, installed source hashes, exact scope and a
completed acceptance or rollback receipt all agree. Other desired-state changes
remain denied; the older documentation-install primitives stay byte-identical.

The final local regression run passed 168 tests with three Root-only tests skipped
in that unprivileged run. The separate disposable Root fixture passed filesystem
bootstrap interruptions, actual file-bind recovery and tracked SQL-helper timeout
cleanup. GitHub's protected-candidate checks remain a separate release gate.

Production acceptance still requires one real consent, controlled native execution
and the live evidence above. Nothing in this document represents those as complete.

### Actual production-peer isolation scope, November 22, 2026

The journal migration replaces three canonical audit producers but does not
mutate the separately signed preproduction shadow. The exact reviewed
`protected_peer_inventory` binds all six peer image IDs, source/release
identity, running state and full production health. It permits only an
otherwise exact and fully network/provider-isolated 4 GiB preproduction
shadow to report its *actual* UNHEALTHY state as a recorded advisory rather
than block unrelated Root SQLite recovery. This does not alter native drift,
the circuit breaker or Stage E general peer-health policy. Shadow isolation,
resource, memory, image or security drift still denies Root cutover.

### OOM-stopped, exactly isolated preproduction shadow (November 22, 2026)

Live Docker evidence shows the separately bounded `jason-pmv4-shadow-gateway` exited at **06:42:03 EST**, with `OOMKilled=true`, exit code 137, and zero restarts. The exact already-reviewed preproduction image/source, 4 GiB memory cap, CPU limit, `NetworkMode=none`, read-only filesystem, dropped all capabilities, disabled provider mutation, no production bind mounts and `RestartPolicy=no` remain unchanged. All five actual production peers remain running with exact identity and required health. The Root production drift reported no findings for this isolated preproduction shadow.

The audit-only peer inventory now also accepts this one **specific observed exit state**, without restarting it and without pretending it is healthy. A stopped preproduction shadow must have all the exact isolation controls, `Status=exited`, `OOMKilled=true`, `ExitCode=137`, `Pid=0`, `RestartCount=0` and its previously observed unhealthy state. Its actual `running=false`, OOM and exit code are recorded in the Owner-bound release scope. A production peer that stops, a shadow that exits for another reason, any changed image/capability/port/mount/source/security setting, or any unknown state **still denies** the Root release. This is not a Stage E operational acceptance exception; shadow health/recovery is a separate objective and is not silently remediated by the audit migration.


### November 22, 2026 — exact ChatGPT Owner-signed adoption and production freeze

The Owner explicitly authorized lifting the hold for the audit-journal objective while continuing the same migration; this is **not** an instruction to remove all other production safeguards. The independently inspected production freeze marker is a UID1000, mode0600 file at /var/lib/jason/openclaw/release-manager/production-deployment-freeze. Its status is active, scope manual-and-automatic-production-promotions, and it requires an Owner exact-SHA decision. The archive Root installer already **hash-pins this freeze marker** (along with the separate unattended selector hold and PMv3 engineering pause); deleting or changing it would invalidate the reviewed Root admission, introduce unintended cross-project permission, and breach the original exact-scope plan.

The bounded solution preserves the original global freeze bytes unchanged and treats the signed archive-specific adoption as one separately governed transaction under the original baseline. It cannot promote an unrelated source change or remove the global freeze.

The recovery succeeded at ~10:33 EST: the already-installed PMv4 native Root transition/readback path independently closed the production breaker with reason root_verified_revalidate, exact LKG d1b8c196dadd4b672ec8ba47075f27bb61c98d63. Four SQLite integrity and restored-authority proofs remain PASS, fast health PASS and drift PASS. The original 93 full-health override was already removed. As of ~11:24 EST, the ~45.6 GB canonical SQLite journal had **not** been migrated, daily timer absent, ~9.5 GB root disk free, ~176 GB free on the selected /srv/jason/archive drive.

**One exact Owner approval, not a CLI device code:** New jason_mcp.approve_audit_journal_adoption() is a distinct guarded MCP tool. It uses the actual existing _release_approval_owner() which independently authenticates the Entra bearer tenant/OID and active AOT Owner principal, and the separately provisioned Ed25519 service signer. A genuine root-staged short-lived offer is required. It signs the exact archive action, reviewed source candidate SHA, rollback SHA, full Root scope SHA, manifest SHA, original freeze SHA and exact staging receipt. It refuses a wrong Owner, tenant, altered offer, provider authorization, stale proof, replay or missing explicit affirmative action. It records only a one-use signed receipt; it never runs Root or deploys anything. It remains **disabled by default** until the separate governed producer/consumer are installed.

**Root must not trust the MCP response or a model message as approval.** tools/audit_journal_signed_owner_bridge.py handles a root-produced private 0400 stage and corresponding al-owned 0600 public offer on the existing authority volume. After the MCP has signed, the Root adopter reads the immutable private stage, enforces source/rollback/scope/freeze and exact six-peer health/capacity checks, independently validates the pinned owner Ed25519 signature, verifies the licensed Owner Entra tenant and OID, and checks the native live preflight a second time. The original audit_journal_install.py then creates its immutable one-use Root approval record **before** invoking the unchanged reviewed migration transaction. The archival component still requires original writers/readers event parity, restored backup, daily rollover, a genuine rollback rehearsal, no open handles, preserved provider outcomes and actual root-disk reclaim. No standing Owner or Root authorization is granted.

**Native Root admission remains an external prerequisite, not a workaround:** The connected Remote Desktop Commander is explicitly non-Root and prohibits privileged shell commands. The live MCP image is the previous approved LKG and therefore does not include the new tool. There are no GitHub self-hosted runners and the current native Root request workers accept only their existing exact whitelisted actions; they cannot consume a journal adoption or install a new Root worker by interpreting a ChatGPT instruction. Source-only commits and CI must not be described as production deployment. A separately authorized, Root-installed exact archive executor/issuer bootstrap must be staged and verified before the guarded MCP tool can be enabled. The Owner has refused further terminal-based device-code flows; this design requires none.

**Isolated acceptance:** The ChatGPT issuer and bridge pass 64 focused real-Ed25519 positive/negative tests, including wrong Owner/tenant/scope/rollback, stale public offers and changed private stage. Actual isolated UID0/no-network/no-host-mount fixture independently verifies Root mode0400 receipt, UID1000 mode0600 publication, root-custody protection, missing-signature denial and one-use refusal. The final combined original journal, rollback, signed Owner, native request, and health suite passed 304 tests. No production code, server, authentication setting, freeze marker or journal data was mutated by this preparation. The candidate still needs protected Main review/CI and a separately governed production Root/issuer installation.


#### Exact native Root executor and rollout boundary

The source-only one-time native bridge is tools/audit_journal_owner_native_worker.py, guarded by root-owned /etc/jason-owner-release/audit-journal-owner-executor-v1.json. Its narrowly scoped temporary systemd service/path templates live in infrastructure/jason-audit-journal-owner-executor. The trust record binds the reviewed worker SHA256, reviewed original installer SHA256, exact candidate source SHA, exact reviewed checkout location, rollback, allowed actions and an expiration no greater than 24 hours. A Root request cannot supply its own executable path, source hash, signing key or command. The original global deployment freeze remains hash-pinned and unchanged. The worker never accepts an arbitrary shell, provider action, generic release, new Root code or changed Main SHA.

After a separately authorized root-signed bootstrap has installed the trusted worker, the UID1000 request producer tools/audit_journal_owner_native_request.py can enqueue exactly audit_archive_stage (read-only Root preflight plus immutable offer publication) or audit_archive_adopt (requires the separately signed exact Owner approval). These are the only two Root actions. The worker reads a mode0600 UID1000-owned request, validates it against the root-only trust record and Main Git blob, then compiles only the independently reviewed original installer from that protected Git source. The original installer carries all Root live checks and its own one-use approval/transaction/rollback policy. The worker publishes bounded statuses, not secrets, and does not report deployment acceptance merely because it queued adoption. The finalized archive release/maintenance timer performs the actual cutover.

The temporary executor requires a **separate authorized bootstrap**, including independently verified licensed Owner approval for that exact Root installation, before its Root-owned service/profile may be installed. The Root installer cannot be bootstrapped from this connected UID1000 remote shell, because that connection blocks privileged commands, and there is no GitHub self-hosted runner or live Jason MCP release/root capability. Changing Desktop Commander blockedCommands, repurposing a PMv4/Catalog Root action, generating an unsigned Owner grant, or using a Docker-root shell would bypass existing safeguards. No such action was attempted. The source is prepared for protected-Main review/CI, but is not a production bootstrap. The authenticated Owner ChatGPT session may authorize exact bootstrap/install once a governed issuer is installed; it does **not** permit treating a normal release approval as arbitrary Root authority. No terminal device-code approval is needed in the proposed normal flow.

When an authorized Root executor exists, complete the process in this order: activate the exact source-pinned Root watcher with recorded rollback, stage the offer and show the Owner the exact candidate/rollback/size/cutover; sign through authenticated ChatGPT Owner OAuth; submit exact adopt; independently inspect the Root result and original journal Root transaction; verify archive event parity, restored backup, live later writes, daily rollover timer, reboot mapping and reclaimed root space; then disable the temporary bootstrap watcher. A failed stage or signer check must not modify the audit database. An interrupted adoption uses only the original one-use, source-pinned bootstrap-recovery and rollback mechanisms; never ask the Owner to reapprove the same successful exact signature because the installer failed after its own one-use claim.

**Latest isolated testing:** 304 broad journal and rollback regressions PASS, 64 signed owner + installer handoff tests PASS, 20 Root worker request and protected-source denial tests PASS, no-network UID0/UID1000 Root-stage fixture PASS, no-network UID0/UID1000 Root native worker fixture PASS. Neither Root fixture mounted the live server or made a production write. Full protected-Main CI and actual native Root-stage execution remain necessary before declaring operational success.
