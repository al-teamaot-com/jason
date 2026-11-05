# KFS AOT-wide copy-count information source

Owner: AOT Copier Operations · 2026-11-03

## Goal
Any authenticated AOT staff member may ask Jason normal read-only questions about KFS copy counts without supplying a spreadsheet or device ID first.

## First-stage supported behavior
- Full-fleet period lists, including all managed devices rather than a first-page subset.
- Top-N fleet usage questions.
- Explicit month or bounded date-range questions such as last 30 days.
- Device-specific historical usage through the existing meter-history/usage capabilities.
- Company, device/equipment ID, serial number, black-and-white usage, color usage, total usage, reading timestamps, and explicit data-quality exceptions.
- Organization-wide AOT observe authority; no approval is required for these reads.

## Source and safety boundary
- KFS inventory and KFS meter history are authoritative for this capability.
- No SharePoint lookup is required for current copy-count answers.
- No provider mutation, endpoint action, ticket update, reboot, network change, or other disruptive action is permitted.
- Missing boundaries, new devices, stale data, meter resets, or inconsistent counters are reported rather than estimated.

## Acceptance
1. An arbitrary AOT staff principal routes the same natural-language copy-count request to the governed KFS fleet capability.
2. The fleet path supports at least 435 devices and does not truncate at 100.
3. The same organization-wide observe grant applies to the fleet report, device usage, and meter-history reads.
4. Non-AOT/client-scoped requests remain fail-closed.
5. Production deployment requires a separately authorized exact merged SHA and verified rollback SHA.
