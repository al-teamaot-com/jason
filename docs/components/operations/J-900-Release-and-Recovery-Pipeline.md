# J-900 — Release and Recovery Pipeline

**Version:** 0.1.2
**Status:** Foundation complete
**Owner:** Jason Architecture Authority
**Applies to:** Official Jason validation, release, evidence, and recovery workflows

## 1. Purpose

The Release and Recovery Pipeline turns Jason's release checklist into an executable, fail-closed process.

Its objective is:

> One command produces a validated, evidenced, recoverable Jason release.

The pipeline reduces human memory requirements without weakening governance.

## 2. Governing Principles

1. The correct release path must also be the easiest release path.
2. Validation completes before any recovery artifact is created.
3. A failed gate stops the release immediately.
4. Official releases originate from a clean, synchronized `main` branch.
5. Release evidence is generated automatically and retained with recovery artifacts.
6. Recovery is proven through an offline restore and validation, not assumed.
7. Existing repository tools and approved platforms are reused before new functionality is introduced.
8. Secrets, credentials, runtime databases, and generated environments are excluded from release artifacts.
9. Existing recovery directories are never overwritten.
10. Package creation is atomic and incomplete staging output is removed on failure.
11. The release orchestrator coordinates existing components and does not duplicate their business logic.

## 3. Implemented Foundation

The foundation provides four independently testable tools:

- `tools/validate_release.py` — validates the worktree, Kernel tests, CAP-001 tests, documentation assembly, strict MkDocs build, and whitespace;
- `tools/create_recovery_package.py` — creates and verifies the Git bundle, source archive, environment record, release manifest, and SHA-256 checksums;
- `tools/verify_recovery_restore.py` — clones the bundle offline, checks out the exact recorded commit, and runs release validation from the restored repository;
- `tools/release.py` — coordinates the complete governed workflow and emits the final approved or denied result.

The standard command is:

```bash
python3 tools/release.py \
  v0.1.2 \
  "Release Name"
```

The default output location is:

```text
~/Jason-Recovery/<version>/
```

## 4. Proven v0.1.2 Release

The J-900 foundation was proven against commit:

```text
24e2b2650c016741763c3e246b3a23d4f8bf3bab
```

The governed release completed with:

- release validation approved;
- recovery package creation approved;
- Git bundle verification approved;
- SHA-256 verification approved;
- offline restore verification approved;
- restored Kernel and CAP-001 tests approved;
- restored strict documentation build approved;
- clean synchronized `main` confirmed.

The verified recovery package is stored at:

```text
/home/al/Jason-Recovery/v0.1.2
```

## 5. Failure Behavior

The pipeline fails closed.

It must not overwrite a recovery package, retain an apparently complete failed package, or approve an unverified restore. Error output identifies the failed stage without exposing secrets.

## 6. Deferred Scope

The foundation does not yet:

- create or push tags;
- create GitHub releases;
- upload evidence packages to external durable storage;
- sign release artifacts;
- enforce external approvals;
- update a `latest` recovery pointer;
- publish test logs or a rendered release report;
- emit a separate machine-readable final release report.

These remain governed future increments and do not block foundation completion.

## 7. Change Control

Changes that weaken a required gate, alter release authority, permit releases from dirty or unsynchronized branches, overwrite recovery artifacts, or bypass restore verification require architectural review and an ADR.

## 8. Foundation Acceptance

The J-900 foundation is complete because:

1. one command coordinates validation, package creation, and restore verification;
2. stage ordering is deterministic;
3. every required stage fails closed;
4. the recovery package contains verifiable source and repository history;
5. the restored commit must equal the package commit;
6. the restored repository executes its own validation command;
7. focused J-900 tests cover successful and denied paths;
8. Kernel, CAP-001, J-900, and strict documentation validations pass;
9. a real v0.1.2 recovery package was created and restore-verified.

## 9. References

- `10-Milestones/M-001-Kernel-Foundation.md`
- `10-Milestones/M-002-Release-and-Recovery-Pipeline.md`
- `04-Standards/J-401-Adaptive-Build-Method.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
- `.github/workflows/validate.yml`
