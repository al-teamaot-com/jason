# Project Jason — native scoped-backport deployment-helper dependency repair

**Source-only engineering; protected Owner-approved installation required.**

## Actual observed incident, November 19, 2026

1. The first authenticated scoped root install succeeded (root service attested).
2. A separate, authenticated four-unit desired-state correction completed by
   **15:15:31 EST**; protected production breaker subsequently read **CLOSED**
   and independent drift **PASS / zero problems**. User's later re-run of
   that already consumed one-time correction was correctly denied
   `SCOPED_DRIFT_SCOPED_ROOT_INSTALL_IDENTITY_DRIFT` because the private root
   trust policy now cites corrected main
   `24651789b5fc8ee79d46b54151ac36280e83efad`.
   **Never replay or weaken that earlier exact approval.**
3. Native preproduction staging request
   `2d48d4959ae74faa952d5d8b800c07b5`
   was processed independently but denied with
   `SCOPED_BACKPORT_NATIVE_SCOPED_DEPLOY_PREFLIGHT_FAILED`. Native release
   `release-87dfd07ae67d2d99` remained **not eligible / not approved**.
4. Read-only reproduction of the exact installed deployment executable:
   `/usr/bin/python3 /usr/local/lib/jason/scoped-backport/tools/deploy_live_container.py --help`
   fails at import time with
   `ModuleNotFoundError: No module named 'pmv4_mcp_projection'`.
   `tools/pmv4_mcp_projection.py` was present in the GitHub reviewed source,
   but was **omitted** from the original root bootstrap's installed `FILES`.
   A previously successful manual source-worktree preflight accidentally
   masked the missing installed sibling. This is not an OpenBao credential,
   image, Ticket Core or PMv4 production error.

## Narrow production-safe source correction

- Future original root bootstrap sources now include
  `tools/pmv4_mcp_projection.py`.
- The root native host's exact private `ROOT_POLICY_FIELDS` and
  `INSTALL_FILES` now also include
  `native_mcp_projection_sha256`, verified against the root-owned installed
  helper before **every** native stage/promotion/recovery action.
- The one-time `scoped_backport_projection_helper_repair.py` fixes an
  **already installed** root boundary by:
  1. enforcing exact reviewed GitHub source SHA and CI SHA, clean checkout,
     protected-main ancestry, and byte-identical, reviewed scope after
     unrelated main-branch merges;
  2. independently reading the old root-private installation policy and
     public attestation, verifying the pinned prior install SHA, approved
     drift/freeze/rollback, root-owned installed Docker code, no active scoped
     offer or unresolved transaction, active dedicated scoped listeners, and
     unchanged protected container identities;
  3. obtaining **one fresh AOT Entra Owner authentication and affirmative exact
     maintenance scope**, bound to source, file hashes, old/new policy hashes,
     LKG SHA and freeze hash, and durably recording one-use approval before
     any mutation;
  4. pausing **only** the dedicated scoped request path and recovery timer
     under the existing global production transaction lock, requiring scoped
     oneshot workers quiescent;
  5. installing only one root-owned, mode 0444 new source file
     `pmv4_mcp_projection.py`; replacing only the root-owned immutable
     `scoped_backport_native_host.py`; and replacing only the private
     install-policy digest record and matching public attestation;
  6. verifying native deployment helper `--help` in a clean, environment-
     independent Python process, independently attesting the installed
     root handler, verifying original protected container IDs and freeze;
  7. reversing only exact known file bytes if any required installation
     check fails, without overwriting foreign changes or requesting another
     approval;
  8. running the trusted root `--probe-stage` as a **nonmutating diagnostic**
     after installation; this probe never creates release eligibility, obtains
     Owner production approval, or performs a Graph POST.

**Explicitly excluded:** rebuilding or replacing jason-runtime,
jason-mcp-pilot, Ticket Core or Shadow Gateway, granting Graph consent,
writing Entra groups, touching OpenBao credentials, restarting containers,
modifying the production freeze, closing a breaker without independent root
revalidation, and authorizing production promotion.

The maintenance approval is distinct from both prior single-use installation
approvals and later one-use native production release approval. Do not treat
any prior successful sign-in or Owner confirmation as standing approval.

## Acceptance and release flow

1. Merge source only after full source/CI/GitGuardian review, a standalone
   install-layout regression, and root policy exact-schema tests.
2. Prepare clean protected-main checkout with exact source and reviewed CI SHAs.
3. Obtain local authenticated Owner action once for this exact new root
   dependency repair. First run `--check` read-only if needed; no Owner
   device-code login on check.
4. Verify root attestation, import `--help`, original protected container
   IDs/freeze, root-owned audit success and read-only stage probe.
5. From the **newly verified** root installation, issue a fresh native
   `scoped-backport-stage` request; wait for independent root eligibility
   and verify root/public exact record. Use no blind retry.
6. Only an eligible native release may be submitted for **separate exact-SHA,
   one-use Owner production approval**. Release Manager must consume and
   independently validate its signature, paired rollback image IDs and
   production lock before any promotion.
7. Verify post-release runtime/MCP health, active Entra group capabilities,
   all protected PMv4 processes, unchanged provider permissions, and rollback
   evidence. Never claim a deployed or working Graph write from source tests.

The engineering repair must not be described as a production deployment until
the specific root-owned receipt and release-manager results exist.

## Parallel integration and CI coordination

PR #2654 performs a separate catalog Owner-canary admission repair. Its only
file-level overlap with this isolated scoped release-control fix is the
additive test-step registration in
`.github/workflows/security-regressions.yml`. Review confirmed the
new catalog tests and the new standalone native-helper packaging test use
distinct test files and exercise separate governed components. Both steps
must remain in the protected workflow after integration, and neither PR
may be treated as an approval for the other's production root writes.
The PR bodies explicitly record `Integration coordination: #2654` and
`Integration coordination: #2655`, respectively, so the repository's
change-integration gate can preserve both independent validations.
