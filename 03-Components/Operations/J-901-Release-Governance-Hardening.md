# J-901 — Release Governance Hardening

**Version:** 0.1
**Status:** Foundation in progress
**Owner:** Jason Architecture Authority
**Applies to:** Governed Jason release preparation and evidence readiness

## 1. Purpose

J-901 makes documentation a required release input rather than a post-release activity.

The governing objective is:

> A release cannot begin until its approved release record already exists in the merged repository.

## 2. Documentation Readiness Gate

Before tests, package creation, or restore verification, the release pipeline must verify that:

1. exactly one milestone record matches the requested version;
2. the record's `Release Name` matches the requested release name;
3. the record status is `Complete` or `Approved`;
4. the record is included in MkDocs navigation;
5. strict documentation validation remains part of the normal release validator.

A compliant release record includes metadata in this form:

```text
**Version:** 0.1.4
**Release Name:** Release Governance Hardening
**Status:** Complete
**Owner:** Jason Architecture Authority
```

## 3. Required Sequence

```text
Implementation complete
    -> Release documentation complete
    -> Documentation navigation complete
    -> Merge to main
    -> Documentation readiness gate
    -> Release validation
    -> Recovery package creation
    -> Offline restore verification
    -> Approved release result
    -> Tag exact packaged commit
```

## 4. Failure Behavior

The gate fails closed when the release record is missing, duplicated, incomplete, named differently, versioned differently, or absent from navigation.

No recovery artifact may be created after a documentation-readiness denial.

## 5. Deferred Scope

This foundation does not yet generate `release-report.json`, create tags, publish GitHub Releases, upload evidence externally, or sign artifacts.

## 6. Acceptance Criteria

The foundation is complete when:

1. documentation readiness executes before release validation;
2. a missing or incomplete record denies release;
3. version and release-name mismatches deny release;
4. navigation omission denies release;
5. successful releases report the verified documentation path;
6. focused tests cover approval and each fail-closed boundary;
7. existing Kernel, CAP-001, J-900, J-901, and strict documentation validations pass.

## 7. References

- `03-Components/Operations/J-900-Release-and-Recovery-Pipeline.md`
- `10-Milestones/M-002-Release-and-Recovery-Pipeline.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
