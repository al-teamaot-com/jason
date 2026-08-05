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

## 4. Implemented Foundation

The validation foundation provides a deterministic command that:

- confirms the repository is a Git worktree;
- confirms the working tree is clean;
- runs the complete Kernel test suite;
- runs the complete CAP-001 test suite;
- assembles the generated documentation workspace;
- runs the strict MkDocs build;
- runs the Git whitespace check;
- emits ordered step results and a final summary;
- exits nonzero on the first failed required gate;
- performs no tag or remote mutation.

The command is:

```bash
python3 tools/validate_release.py
```

## 5. Recovery Package Foundation

The recovery package increment adds deterministic, local package creation after successful validation.

The command is:

```bash
python3 tools/create_recovery_package.py \
  v0.2.0 \
  "Release Name"
```

By default, the verified package is written to:

```text
~/Jason-Recovery/<version>/
```

The package contains:

- a complete Git bundle containing all local branches, tags, and reachable history;
- a source archive that excludes Git metadata, virtual environments, build output, caches, and generated Python files;
- an environment manifest containing the commit, platform, Python version, Git version, and installed test and documentation packages;
- a machine-readable `release-manifest.json`;
- `SHA256SUMS.txt` covering the bundle, source archive, environment manifest, and release manifest.

The builder:

- normalizes versions to a leading `v`;
- rejects empty or path-unsafe versions;
- resolves and records the represented commit;
- verifies the Git bundle before publishing the package directory;
- calculates and verifies SHA-256 checksums;
- stages output under a temporary directory;
- removes incomplete staging output on failure;
- fails closed when the destination version already exists;
- does not create or push a tag;
- does not upload artifacts to external storage.

## 6. Deferred Scope

The foundation does not yet:

- create or push tags;
- create GitHub releases;
- perform a full restore simulation from the generated bundle;
- upload evidence packages to durable storage;
- sign release artifacts;
- enforce external approvals;
- update a `latest` recovery pointer;
- publish test logs or a rendered release report.

These remain later J-900 increments after local package creation is proven.

## 7. Failure Behavior

The pipeline fails closed.

It must not create a release tag, publish a release, overwrite a recovery package, or leave an apparently complete package when any required step fails.

Error output must identify the failed step and preserve enough context for remediation without exposing secrets.

## 8. Change Control

Changes that weaken a required gate, alter release authority, permit releases from dirty or unsynchronized branches, overwrite recovery artifacts, or bypass recovery verification require architectural review and an ADR.

## 9. Recovery Package Acceptance Criteria

The recovery package foundation is complete when:

1. successful validation can be followed by one package-creation command;
2. package output is deterministic in structure;
3. existing release directories fail closed;
4. source archives exclude repository metadata and generated environments;
5. Git bundles verify successfully;
6. checksums are generated and verified before the final directory is published;
7. manifests record version, release name, commit, source ref, creation time, and artifact metadata;
8. focused tests cover version handling, successful creation, exclusions, checksums, and overwrite prevention;
9. the Kernel, CAP-001, J-900, and strict documentation validations remain passing.

## 10. References

- `10-Milestones/M-001-Kernel-Foundation.md`
- `04-Standards/J-401-Adaptive-Build-Method.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
- `.github/workflows/validate.yml`
