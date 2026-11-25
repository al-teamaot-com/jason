# PMv4 JSON — governed live-read replay evidence

## Section Goal
Independently validate the read-only JSON parsing and branch logic against a
**real Jason MCP governed provider observation** without running or modifying
the protected production Ticket Core, creating JSON active versions, or
performing provider mutation.

## Controlled live evidence
November 19, 2026: the existing `management.alert.search`,
`management.site.search`, and `endpoint.device.read` capabilities returned
`succeeded` via Jason's existing Central Orchestrator. A single
current Windows Time mismatch alert was selected and its exact DRMM site ID,
Autotask company mapping, device UID and hostname were cross-checked.
Authoritative endpoint state was **offline**. Unrelated records, user details,
addresses, IPs, service secrets and device inventories were discarded before
creating the private, minimal local replay fixture.

The sanitized minimal fixture is stored **only** in a restricted, ignored
development evidence directory on the authorized Jason host (not in this
public repository). Its SHA256:
`474e4b373729fdf9436277c70b8367cc66cd8a7134ca3804e33803c74185f487`.

The frozen source candidate `windows_time_source@0.1.0-migration.1`
had file SHA256:
`76d902efd3e490381ad655cb0a862e4c831286147f8c68e1d66fe9ecc22ef1ce`.

## Exact result
- The isolated canonical JSON interpreter returned
  `completed_readonly / classified_waiting`, classification
  `WAITING_DEVICE_ACCESS`.
- The actual existing pure Windows Time legacy classifier returned the
  **same classification and exact evidence fingerprint** on the same input.
- Restart/read-only checkpoint reuse performed no repeated observations.
- No DRMM alert resolution, Autotask write, endpoint command, service restart,
  reboot, JSON registry activation, or protected Core modification.
- The three separately governed live reads were obtained through ChatGPT's
  Jason connector and then replayed into the isolated source runner.
  **The runner did not itself connect directly to a live provider**.

## Acceptance disposition
**Live-origin evidence replay: PASS for the offline/waiting branch.**

**Actual autonomous preproduction runtime-to-live-ObservePort wiring:
NOT VERIFIED.**

**Full authored Windows Time Self-Heal migration: NOT ACCEPTED.**

**All 19 production JSON replacements: 0 accepted.**

This evidence cannot substitute for further live provider pilot checks,
separate exact Owner approval for a later action, or source-to-runtime
activation and rollback acceptance.
