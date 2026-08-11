# Project Jason Governance — Authority Map

**Status:** Active governance documentation index  
**Owner:** Jason Architecture Authority  
**Higher authority:** `docs/foundation/J-002-Constitution.md`

## Purpose

This directory contains governance records below the Constitution. Nothing in this directory may silently amend, renumber, or override the Jason Constitution.

## Canonical governance record

`J-003-Decision-Architecture.md` defines Jason's mandatory evidence-, authority-, policy-, safety-, and outcome-oriented decision process. It is interpreted subject to the Constitution and approved ADRs/standards.

## Constitutional boundary

The current Constitution is `docs/foundation/J-002-Constitution.md`. Its numbered Articles are authoritative for constitutional article identity.

A separate historical file named `ARTICLE_VII_PLATFORM_INTEGRITY.md` also exists in this directory and labels itself “Approved constitutional article.” That designation conflicts with the current J-002 Constitution, whose Article VII is **Knowledge as an Asset**.

Until that historical record is formally reconciled through governance:

- it must **not** be treated as Article VII of the current Constitution;
- it must not override J-002;
- its platform-integrity requirements may be used as supporting governance context only where they are consistent with current constitutional/architecture records;
- durable requirements unique to that record should be reconciled into an appropriate canonical Constitution, architecture, standard, or governance owner before the historical record is archived or retired.

The conflict is tracked in `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md`.

## Governance precedence

When governance material conflicts, use this order:

1. `docs/foundation/J-002-Constitution.md`
2. approved constitutional amendments explicitly incorporated into or linked by J-002
3. approved governance records such as `J-003-Decision-Architecture.md`
4. approved ADRs and architecture/standards within their subject boundaries
5. supporting/historical governance records

## Change rule

Do not create a free-standing “constitutional article” file that is not explicitly incorporated into the Constitution's authoritative amendment/versioning process.

Future constitutional changes must make the resulting authoritative article numbering and status unambiguous in J-002 or its formally governed successor.