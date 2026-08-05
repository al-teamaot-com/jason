# J-901 — Release Governance Hardening

**Version:** 0.2
**Status:** Foundation in progress
**Owner:** Jason Architecture Authority
**Applies to:** Governed Jason release preparation and evidence readiness

## 1. Purpose

J-901 makes documentation and release evidence required parts of the release workflow rather than post-release activities.

The governing objective is:

> A release cannot begin without an approved release record and cannot finish without verified evidence artifacts.

## 2. Documentation Readiness Gate

Before tests, package creation, or restore verification, the release pipeline verifies that:

1. exactly one milestone record matches the requested version;
2. the record's `Release Name` matches the requested release name;
3. the record status is `Complete` or `Approved`;
4. the record is included in MkDocs navigation;
5. strict documentation validation remains part of the release validator.

A compliant release record includes:

```text
**Version:** 0.1.4
**Release Name:** Release Governance Hardening
**Status:** Complete
**Owner:** Jason Architecture Authority
```

## 3. Release Evidence Artifacts

After restore verification and exact commit comparison succeed, the pipeline writes these files into the recovery package:

- `release-report.json` — machine-readable release evidence;
- `release-summary.md` — human-readable approved release summary;
- updated `SHA256SUMS.txt` — checksums covering the complete package, including both evidence files.

The JSON report records:

- schema version;
- release version and name;
- release commit and timestamp;
- approved documentation path;
- validation stage identifiers;
- recovery artifact names, hashes, and sizes;
- restored commit and approval status;
- final governed release status.

The writer refuses to overwrite existing evidence and fails closed when commit alignment or checksum verification fails.

## 4. Required Sequence

```text
Implementation complete
    -> Release documentation complete
    -> Documentation navigation complete
    -> Merge to main
    -> Documentation readiness gate
    -> Release validation
    -> Recovery package creation
    -> Offline restore verification
    -> Exact commit comparison
    -> Release evidence generation
    -> Complete package checksum verification
    -> Approved release result
    -> Tag exact packaged commit
```

## 5. Failure Behavior

The pipeline fails closed when documentation is missing or inconsistent, a required release stage fails, restored and packaged commits differ, evidence already exists, or final package checksums do not verify.

No approved result may be emitted without both release evidence artifacts.

## 6. Deferred Scope

This foundation does not yet create tags, publish GitHub Releases, upload evidence externally, sign artifacts, or enforce external approval identities.

## 7. Acceptance Criteria

The foundation is complete when:

1. documentation readiness executes before release validation;
2. incomplete or inconsistent documentation denies release;
3. release evidence executes only after restore verification;
4. `release-report.json` records governed stage and artifact evidence;
5. `release-summary.md` provides a concise human-readable result;
6. final checksums cover both evidence artifacts;
7. evidence generation failures deny the release;
8. focused tests cover approval and fail-closed boundaries;
9. existing Kernel, CAP-001, J-900, J-901, and strict documentation validations pass.

## 8. References

- `03-Components/Operations/J-900-Release-and-Recovery-Pipeline.md`
- `10-Milestones/M-002-Release-and-Recovery-Pipeline.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
