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
Release Evidence Generation
    |
    v
Recovery Package Creation
    |
    v
Restore Simulation and Validation
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

## 6. Restore Simulation Foundation

The restore verification command is:

```bash
python3 tools/verify_recovery_restore.py \
  ~/Jason-Recovery/v0.2.0
```

The verifier:

- reads the release manifest;
- locates the versioned Git bundle;
- creates a disposable workspace;
- clones the repository from the bundle without using the network;
- checks out the exact commit recorded in the manifest;
- verifies the restored `HEAD` matches the recorded commit;
- attaches the approved local test and documentation environments by ignored symbolic links;
- executes the restored repository's own `tools/validate_release.py` command;
- removes the disposable workspace unless retention is explicitly requested;
- fails closed when the manifest, bundle, commit, clone, checkout, or validation is invalid.

The environment links are only validation dependencies. They are excluded through the restored repository's local `.git/info/exclude` and do not modify tracked content.

For troubleshooting, a caller may supply `--workspace` and `--retain-workspace`. Production release workflows should normally use automatic cleanup.

## 7. Deferred Scope

The foundation does not yet:

- create or push tags;
- create GitHub releases;
- upload evidence packages to durable storage;
- sign release artifacts;
- enforce external approvals;
- update a `latest` recovery pointer;
- publish test logs or a rendered release report;
- combine validation, package creation, restore verification, tagging, and publication into one final release command.

## 8. Failure Behavior

The pipeline fails closed.

It must not create a release tag, publish a release, overwrite a recovery package, retain an apparently complete failed package, or approve an unverified restore.

Error output must identify the failed step and preserve enough context for remediation without exposing secrets.

## 9. Change Control

Changes that weaken a required gate, alter release authority, permit releases from dirty or unsynchronized branches, overwrite recovery artifacts, or bypass restore verification require architectural review and an ADR.

## 10. Restore Simulation Acceptance Criteria

The restore simulation foundation is complete when:

1. one command restores a package into a disposable workspace;
2. the clone uses the generated Git bundle rather than a remote repository;
3. the restored commit exactly matches the release manifest;
4. the restored repository executes its own release validation command;
5. failed clone, checkout, commit verification, or validation stops the process;
6. disposable workspaces are removed by default;
7. optional retention is explicit;
8. focused tests cover missing evidence, workspace conflicts, successful sequencing, and command failure;
9. existing Kernel, CAP-001, J-900, and strict documentation validations remain passing.

## 11. References

- `10-Milestones/M-001-Kernel-Foundation.md`
- `04-Standards/J-401-Adaptive-Build-Method.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
- `.github/workflows/validate.yml`
