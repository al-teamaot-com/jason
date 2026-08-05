# J-900 — Release and Recovery Pipeline

**Status:** Foundation in progress
**Owner:** Jason Architecture Authority
**Applies to:** Official Jason validation, release, evidence, and recovery workflows

## 1. Purpose

The Release and Recovery Pipeline turns Jason's release checklist into an executable, fail-closed process.

Its objective is:

> One command produces a validated, evidenced, recoverable Jason release.

The pipeline reduces human memory requirements without weakening governance.

## 2. Governing Principles

1. The correct release path must also be the easiest release path.
2. Validation completes before any tag or recovery artifact is created.
3. A failed gate stops the release immediately.
4. Official releases originate from a clean, synchronized `main` branch.
5. Release evidence is generated automatically and retained with recovery artifacts.
6. Recovery is not assumed; generated bundles and checksums must be verified.
7. Existing repository tools and approved platforms are reused before new functionality is introduced.
8. Secrets, credentials, runtime databases, and generated environments are excluded from release artifacts.
9. Existing recovery directories are never overwritten.
10. Package creation is atomic: incomplete staging output is removed on failure.
11. A recovery package is not approved until a disposable restored repository passes release validation.
12. The release orchestrator coordinates existing components and does not duplicate their business logic.

## 3. Pipeline Boundary

```text
Release Request
    |
    v
Preflight Validation
    |
    v
Repository and Test Validation
    |
    v
Documentation Validation
    |
    v
Recovery Package Creation
    |
    v
Restore Simulation and Validation
    |
    v
Governed Release Summary
    |
    v
Tag and Publish
    |
    v
Approved Release Result
```

The pipeline coordinates existing Git, Python, pytest, MkDocs, archive, checksum, and repository capabilities. It does not redefine those tools.

## 4. Implemented Validation Foundation

The validation foundation provides:

```bash
python3 tools/validate_release.py
```

It confirms the worktree is clean, runs Kernel and CAP-001 tests, assembles documentation, builds MkDocs in strict mode, checks whitespace, and fails on the first required gate.

## 5. Implemented Recovery Package Foundation

The package command is:

```bash
python3 tools/create_recovery_package.py \
  v0.2.0 \
  "Release Name"
```

By default, output is written to `~/Jason-Recovery/<version>/` and contains a complete Git bundle, source archive, environment manifest, release manifest, and verified SHA-256 checksums.

The builder refuses to overwrite existing release directories, excludes generated environments and repository metadata from the source archive, verifies the bundle, stages output atomically, and removes incomplete staging output on failure.

## 6. Implemented Restore Simulation Foundation

The restore verification command is:

```bash
python3 tools/verify_recovery_restore.py \
  ~/Jason-Recovery/v0.2.0
```

The verifier clones the generated bundle into a disposable workspace, checks out the exact manifest commit, attaches approved local validation environments through ignored symbolic links, runs the restored repository's own release validation command, and removes the workspace by default.

## 7. Release Orchestrator Foundation

The governed release command is:

```bash
python3 tools/release.py \
  v0.2.0 \
  "Release Name"
```

The orchestrator is intentionally thin. It coordinates, in order:

1. the existing `ReleaseValidator`;
2. the existing `RecoveryPackageBuilder`;
3. the existing `RecoveryRestoreVerifier`;
4. exact commit comparison between the package and restored repository;
5. a concise final release summary.

The orchestrator:

- emits one final approved result only after every stage succeeds;
- identifies the failed stage when a component denies the release;
- returns a nonzero process exit on failure;
- does not reimplement validation, package, checksum, or restore logic;
- does not create or push tags;
- does not publish a GitHub release;
- does not overwrite an existing recovery package.

## 8. Deferred Scope

The foundation does not yet:

- create or push tags;
- create GitHub releases;
- upload evidence packages to durable storage;
- sign release artifacts;
- enforce external approvals;
- update a `latest` recovery pointer;
- publish test logs or a rendered release report;
- emit a separate machine-readable final release report.

## 9. Failure Behavior

The pipeline fails closed.

It must not create a release tag, publish a release, overwrite a recovery package, retain an apparently complete failed package, or approve an unverified restore.

Error output must identify the failed stage and preserve enough context for remediation without exposing secrets.

## 10. Change Control

Changes that weaken a required gate, alter release authority, permit releases from dirty or unsynchronized branches, overwrite recovery artifacts, or bypass restore verification require architectural review and an ADR.

## 11. Release Orchestrator Acceptance Criteria

The orchestrator foundation is complete when:

1. one command coordinates validation, package creation, and restore verification;
2. the orchestrator reuses existing tested components rather than duplicating their logic;
3. stage ordering is deterministic;
4. validation failure prevents package creation;
5. package failure prevents restore verification;
6. restore failure denies the release;
7. the restored commit must equal the package commit;
8. successful execution prints version, release name, commit, recovery location, and approved status;
9. focused tests cover success and every fail-closed stage;
10. existing Kernel, CAP-001, J-900, and strict documentation validations remain passing.

## 12. References

- `10-Milestones/M-001-Kernel-Foundation.md`
- `04-Standards/J-401-Adaptive-Build-Method.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
- `.github/workflows/validate.yml`
