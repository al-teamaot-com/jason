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

The former file `ARTICLE_VII_PLATFORM_INTEGRITY.md` historically labeled itself an “Approved constitutional article,” but the current Constitution's Article VII is **Knowledge as an Asset**. That historical numbering conflict has been formally reconciled.

Disposition:

- the current J-002 Constitution and its Article VII remain unchanged;
- the former Platform Integrity record is preserved as historical/superseded evidence at `docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md`;
- its durable platform-integrity requirements are governed by `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` at the standards layer;
- the archived record no longer has current constitutional or governance authority; and
- the reconciliation is tracked as resolved in `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md`.

This preserves the earlier approved intent without creating a second Article VII or silently discarding durable requirements.

## Governance precedence

When governance material conflicts, use this order:

1. `docs/foundation/J-002-Constitution.md`
2. approved constitutional amendments explicitly incorporated into or linked by J-002
3. approved governance records such as `J-003-Decision-Architecture.md`
4. approved ADRs and standards such as J-405 within their subject boundaries
5. canonical architecture within its subject boundaries
6. supporting/historical governance records

## Change rule

Do not create a free-standing “constitutional article” file that is not explicitly incorporated into the Constitution's authoritative amendment/versioning process.

Future constitutional changes must make the resulting authoritative article numbering and status unambiguous in J-002 or its formally governed successor.
