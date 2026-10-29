# Managed read-only triage note updates: exact title acceptance

## Confirmed defect

Production Jason stored its own read-only investigation notes on Autotask
tickets T20261028.0015 and T20261028.0048. Authorized readback confirmed
the existing note bodies match the exact local managed-note ownership
fingerprints. Updating those notes nevertheless fails at execution-plan
construction with the explicit denial AUTOTASK_MANAGED_NOTE_TITLE_NOT_ALLOWED.

The managed-note update provider allowed GPT Insights and Jason Activity only,
while the normal autonomous triage writer intentionally created notes titled
"Jason - Governed Read-Only Investigation". This was an inconsistent local
contract, not an unrelated account permission problem or an indication that a
technician had modified the note.

## Correction and safety

Add the one exact title to the provider's approved managed-note names.
Do not add a wildcard or a new prefix, and do not grant write authority for
arbitrary Jason-prefixed, technician-written or client-facing notes.
The existing connector must continue to pre-read the exact note/ticket,
verify internal visibility, the configured Jason API-user creator identity,
current body, and provider-native mutation access; after PATCH it must
read back the exact revised note/body and preserve creator/visibility.

The exact note-title capability metadata is updated to match behavior.
The existing worker stores verified fingerprints and owns its own notes.
No policy expansion for other Autotask objects or autonomous deployment occurs
here.

## Tested

- Exact titled triage note can be updated via deterministic managed-note
  provider test with preflight and post-mutation readback.
- Similar titles containing suffixes remain denied without a PATCH.
- Changed creator identity and externally visible note remain denied.
- Existing GPT Insights and Jason Activity tests remain passing.
- Existing release #2146 and production freeze are unchanged.

Live provider-backed write and postflight verification require a separately
approved exact-SHA controlled release; test PASS alone is not production acceptance.
