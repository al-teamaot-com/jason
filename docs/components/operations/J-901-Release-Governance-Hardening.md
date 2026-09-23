# J-901 — Release Governance Hardening

**Version:** 0.3
**Status:** Foundation complete
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
**Release Name:** J-901 Release Governance Hardening
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

## 6. Foundation Completion

The J-901 foundation is complete when merged with milestone record M-003. The completed foundation provides:

- documentation readiness as the first governed release gate;
- exact release-version and release-name matching;
- approved-status and navigation enforcement;
- deterministic release validation;
- verified recovery-package creation;
- offline restore simulation and exact commit comparison;
- machine-readable and human-readable release evidence;
- checksum protection for the complete evidence package;
- fail-closed orchestration with named failure stages.

## 7. Deferred Scope

The completed foundation does not create tags, publish GitHub Releases, upload evidence externally, sign artifacts, or enforce external approval identities.

These remain controlled future increments and do not invalidate the J-901 foundation.

## 8. Acceptance Evidence

The foundation was validated through:

1. focused J-900 and J-901 tests;
2. complete Kernel and CAP-001 regression validation;
3. strict documentation assembly and build validation;
4. a disposable committed release record;
5. a complete governed release execution;
6. verified `release-report.json` internal consistency;
7. verified `release-summary.md` generation;
8. checksum verification covering all recovery and evidence artifacts;
9. cleanup that returned the source branch to a clean state.

## 9. References

- `10-Milestones/M-003-Release-Governance-Hardening.md`
- `03-Components/Operations/J-900-Release-and-Recovery-Pipeline.md`
- `10-Milestones/M-002-Release-and-Recovery-Pipeline.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
