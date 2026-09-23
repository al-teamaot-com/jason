# M-003 — Release Governance Hardening

**Version:** 0.1.4
**Release Name:** J-901 Release Governance Hardening
**Status:** Complete
**Owner:** Jason Architecture Authority

## 1. Milestone Declaration

The J-901 Release Governance Hardening foundation is complete.

Jason's governed release command now requires approved release documentation before execution and produces checksum-protected machine-readable and human-readable evidence before reporting approval.

## 2. Delivered Foundation

The milestone includes:

- documentation readiness as the first release gate;
- exact release-version and release-name matching;
- approved release-record status enforcement;
- MkDocs navigation enforcement for the release record;
- deterministic release validation;
- verified recovery-package creation;
- offline restore simulation;
- exact packaged and restored commit comparison;
- `release-report.json` generation;
- `release-summary.md` generation;
- complete package checksum regeneration and verification;
- fail-closed evidence generation with a named release stage;
- refusal to overwrite existing release evidence.

## 3. Governed Release Sequence

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
    -> Complete checksum verification
    -> Approved release result
    -> Tag exact packaged commit
```

## 4. Required Evidence

Every approved release package now contains:

- a complete Git bundle;
- a source archive;
- environment details;
- `release-manifest.json`;
- `release-report.json`;
- `release-summary.md`;
- `SHA256SUMS.txt` covering all required artifacts.

The machine-readable report records the approved documentation path, validation stages, artifact hashes and sizes, restored commit, release commit, timestamps, and final status.

## 5. Acceptance Evidence

The foundation was proven with a disposable committed release record and a complete governed release execution.

The validation demonstrated that:

- all focused release tests passed;
- full Kernel and CAP-001 regressions passed;
- strict documentation validation passed;
- documentation readiness approved the exact record;
- recovery creation and restore verification passed;
- packaged and restored commits matched;
- JSON release evidence was internally consistent;
- Markdown release evidence was generated;
- every recovery and evidence artifact passed SHA-256 verification;
- disposable release material was removed;
- the source branch remained clean.

## 6. Change-Control Boundary

Future release-system changes may extend the governed sequence but must not bypass or weaken documentation readiness, release validation, recovery verification, exact commit comparison, evidence generation, or complete checksum verification without architectural review and an ADR.

## 7. Deferred Work

This milestone intentionally does not include:

- automatic Git tag creation;
- GitHub Release publication;
- external evidence upload;
- artifact signing;
- external approval-identity enforcement;
- deployment execution.

These are future controlled increments and do not invalidate this milestone.

## 8. References

- `03-Components/Operations/J-901-Release-Governance-Hardening.md`
- `03-Components/Operations/J-900-Release-and-Recovery-Pipeline.md`
- `10-Milestones/M-002-Release-and-Recovery-Pipeline.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
