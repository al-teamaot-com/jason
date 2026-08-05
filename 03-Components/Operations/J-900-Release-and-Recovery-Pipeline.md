# J-900 — Release and Recovery Pipeline

**Status:** Proposed foundation design
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
Recovery Verification
    |
    v
Tag and Publish
    |
    v
Approved Release Result
```

The pipeline coordinates existing Git, Python, pytest, MkDocs, archive, checksum, and repository capabilities. It does not redefine those tools.

## 4. Foundation Scope

The first foundation provides a deterministic validation command that:

- confirms the repository is a Git worktree;
- confirms the working tree is clean;
- reports branch and commit state;
- runs the complete Kernel test suite;
- runs the complete CAP-001 test suite;
- assembles the generated documentation workspace;
- runs the strict MkDocs build;
- runs the Git whitespace check;
- emits ordered step results and a final summary;
- exits nonzero on the first failed required gate;
- performs no tag or remote mutation.

## 5. Deferred Scope

The foundation does not yet:

- create or push tags;
- create GitHub releases;
- create source archives or Git bundles;
- generate checksums or environment manifests;
- perform restore simulations;
- upload evidence packages to durable storage;
- sign release artifacts;
- enforce external approvals.

These are later J-900 increments after the validation engine is proven.

## 6. Failure Behavior

The pipeline fails closed.

It must not create a release tag, publish a release, or overwrite a recovery package when any required validation step fails.

Error output must identify the failed step and preserve enough context for remediation without exposing secrets.

## 7. Change Control

Changes that weaken a required gate, alter release authority, permit releases from dirty or unsynchronized branches, or bypass recovery verification require architectural review and an ADR.

## 8. Acceptance Criteria

The foundation is complete when:

1. one command runs all current required validations;
2. step ordering is deterministic;
3. any failed required command returns a nonzero process exit;
4. successful validation produces a concise final report;
5. no release mutation occurs;
6. focused tests cover success, command failure, repository-state failure, and deterministic ordering;
7. the existing Kernel and CAP-001 suites remain passing;
8. strict documentation validation remains passing.

## 9. References

- `10-Milestones/M-001-Kernel-Foundation.md`
- `04-Standards/J-401-Adaptive-Build-Method.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
- `.github/workflows/validate.yml`
