# Jason AOT Technology Lifecycle Baseline

## Section Goal
Give Jason a deterministic, evidence-backed technology lifecycle policy so client posture reviews can distinguish supported, unsupported, unknown, ESU-covered, and explicitly accepted-exception operating systems without guessing from product names.

## Policy
Vendor security-support dates are the default technical baseline. Jason may call an OS supported only when its exact edition/release is inside the applicable vendor security-support window, or when authoritative evidence establishes an applicable ESU/support entitlement. AOT/client exceptions must be explicit durable evidence and never inferred from continued operation, DRMM presence, or an open/closed ticket.

`unsupported` is a posture gap/proposal trigger, not authority to upgrade, replace, reboot, or otherwise remediate a device.

LTSC/LTSB and other special servicing channels fail to `unknown` unless the exact edition/release is established. Network devices are not evaluated by the Windows lifecycle rules.

## Initial Microsoft baseline as of 2026-09-19
- Windows 10 22H2 general Home/Pro/Enterprise/Education servicing: base support ended 2025-10-14. ESU must be independently evidenced.
- Windows 11 23H2 Home/Pro: support ended 2025-11-11. Enterprise/Education 23H2 remains supported through 2026-11-10.
- Windows 11 24H2 Home/Pro: supported through 2026-10-13; Enterprise/Education through 2027-10-12.
- Windows 11 25H2 Home/Pro: supported through 2027-10-12; Enterprise/Education through 2028-10-10.
- Windows Server 2016: extended support through 2027-01-12.
- Hyper-V Server 2012: extended support ended 2023-10-10. Any ESU/exception must be independently evidenced rather than inferred.

Implementation: `implementation/orchestrator/technology_lifecycle.py`. Tests explicitly prove edition-aware Windows 11 behavior, Windows 10/Hyper-V unsupported handling, Server 2016 support, explicit ESU/exception handling, and fail-closed LTSC behavior.
