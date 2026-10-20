# Safe Release Manager deferrals under authenticated-owner SQLite contention

## Confirmed production failure

On 2026-10-19 18:45 EDT, with protected production ae39bc1d and
owner-approved production-eligible c62da59e, the scheduled
jason-release-manager.service failed with sqlite3.OperationalError:
database is locked in SQLiteIdentityAuthorityStore.__init__.
This was invoked by the owner-mobile-decision consumer before it had
checked if historical signed decisions were already completed.

Read-only incident inspection found exactly six signed receipts in the
mobile approval ledger and six matching immutable processed receipts.
Authority storage is a ~1.8 GB busy SQLite DELETE-journal database.
The old consumer initialized authority and Microsoft-binding schemas on
every 5-minute timer pass even when no decision remained pending.
Failed user-unit drift reopened the protected breaker. Independently,
the exact candidate CCC reported a missing separate material review and
expected pre-deploy runtime/source mismatch.

## Corrective rules

1. After mandatory policy/containment checks, read the immutable signed
   release decision ledger in SQLite read-only mode.
2. Verify every processed marker's exact approval ID and signed evidence
   SHA before selecting unprocessed receipts. When no receipts remain
   unprocessed, return zero without opening or modifying Microsoft
   binding or Jason authority databases.
3. On a genuinely new, cryptographically signed and approved decision,
   resolve the current Entra binding and exact Jason owner identity
   using SQLite mode=ro parameterized SELECT queries. No CREATE,
   schema migration, chmod, implicit identity provisioning, or
   developer-controlled authority substitute. Retain every existing
   signed signature, identity, live organization, policy version, time,
   scope, exact manifest, CCC and processed receipt check unchanged.
4. Retry no authority side effects on a SQLite BUSY/LOCKED error:
   report the precise MobileReleaseEvidenceBusy dependency. The
   unattended Release Manager defers ONE scheduled cycle and leaves
   release/CCC records untouched. All other database errors, invalid
   evidence, revoked identity, policy drift, tampered receipts, or wrong
   release SHA still fail closed. A deferred owner-evidence read never
   becomes an approval.
5. A complete, current CCC report with ONLY the attested exact-owner
   material-review NOT_PROVEN (optionally paired with expected
   pre-mutation runtime-source-alignment NOT_PROVEN) defers the
   scheduled cycle rather than crashing systemd. The CCC row must
   contain the precise canonical missing-review text and exact material
   source paths. Direct promotion still raises and NEVER accepts a
   missing owner review, uncurrent checker, failed provider check, or
   malformed report as PASS.

## Safety, rollout, and acceptance

No live SQLite file was modified or migrated during investigation.
The candidate's existing exact-revision release approval is durable,
and its prior isolated preproduction and rollback certification passed.
Missing CCC material review is a separate authenticated owner action;
neither this code nor conversational approval may fabricate that fact.

Tests include genuine exclusive locks on each of the three SQLite
evidence stores, completed historical receipts under exclusive lock,
successful independently signed review on replay, no identity/schema
writes, canonical marker conflict, missing authority file, CCC missing
review expected-shape and unsafe-shape rejection, direct postflight hard
denial, and timer deferral without deployment.

**Sequence:** Keep this fix PR independent until the already approved
c62da59e release has completed under native exact-owner CCC review,
root-verified breaker recovery, and complete independent postdeployment
CCC and rollback protection. Then rebase/review this patch, prepare a
new source-bound candidate, and obtain separate exact-SHA authorization.
Do not merge first merely to make the current older release obsolete.

Release manager health is not the same as engineering acceptance:
check SUPPORT-OPS-054's new content-addressed read receipts, worker
phase, actual code/test PR or evidence-backed blocker, active capacity
and sustained recovery of seven outstanding engineering commitments.
