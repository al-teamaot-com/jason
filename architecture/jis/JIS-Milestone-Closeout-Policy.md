# JIS Milestone Closeout Policy

**Status:** Active engineering procedure
**Owner:** Jason Architecture Authority
**Applies to:** Major Project Jason implementation milestones

## Purpose

A milestone is not complete merely because its software functions correctly.

Each milestone must conclude with a closeout phase that aligns implementation, testing, production validation, architecture, governance, documentation, and repository state.

The closeout phase preserves knowledge, prevents architectural drift, and creates a stable checkpoint before the next major body of work begins.

## Required Closeout Activities

### 1. Implementation review

Confirm that:

- the approved milestone scope was completed;
- incomplete work is documented;
- temporary debugging code was removed;
- provider-specific exceptions remain isolated;
- no interface bypasses JIS;
- unrelated ideas were moved to the backlog.

### 2. Automated testing

Confirm that:

- focused tests pass;
- full regression tests pass;
- repository validation passes;
- security checks pass;
- test fixtures contain no real credentials or client data.

### 3. Production validation

When applicable, confirm:

- authentication succeeds;
- least-privilege permissions are correct;
- representative read operations succeed;
- write operations remain blocked unless explicitly approved;
- failures are controlled;
- credentials are not displayed or logged;
- production-validation evidence is recorded safely.

### 4. Architecture review

Evaluate whether the milestone discovered:

- reusable infrastructure;
- duplicated implementation patterns;
- unnecessary custom code;
- provider-specific exceptions;
- opportunities to simplify existing components;
- changes that require an Architecture Decision Record.

The review is required. It does not require every implementation to become generic.

### 5. Documentation review

Update the applicable:

- JIS Provider Development Guide;
- Architecture Decision Records;
- provider specifications;
- connector catalog;
- capability catalog;
- secret contracts;
- operational runbooks;
- user-facing CLI or API examples;
- known limitations.

No implementation is complete until it is understandable by a competent engineer who did not write it.

### 6. Repository cleanup

Confirm that:

- the working tree is clean;
- temporary branches are removed;
- obsolete files are removed or clearly deprecated;
- generated files are not tracked;
- documentation has one authoritative location;
- naming is consistent;
- unresolved work is captured outside the completed milestone.

### 7. Governance review

Review:

- identity and authority boundaries;
- client and organization scope;
- secret-store access;
- audit requirements;
- mutation approvals;
- rollback requirements;
- data-separation controls;
- Technology Steward ownership.

### 8. Milestone record

Record:

- what was delivered;
- why the architecture was chosen;
- production-validation status;
- known limitations;
- technical debt introduced or retired;
- the recommended next milestone.

### 9. Version checkpoint

Create an approved release or milestone tag after the closeout pull request is merged and the repository is verified.

## Completion Rule

A new major milestone should not begin until the previous milestone has completed closeout.

Urgent fixes, security work, and operational incidents may proceed when necessary, but they do not replace formal closeout.

## Closeout Review Questions

1. What did the milestone deliver?
2. What was production validated?
3. What architectural decisions were made?
4. What became reusable?
5. What should remain specialized?
6. What custom code became unnecessary?
7. What documentation changed?
8. What technical debt remains?
9. Is the repository clean?
10. What is the next approved milestone?
