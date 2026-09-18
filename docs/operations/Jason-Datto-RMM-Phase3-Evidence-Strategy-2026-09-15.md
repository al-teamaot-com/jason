# Jason Datto RMM Phase 3 Evidence Strategy — 2026-09-15

## Purpose

Record the decision to stop spending time trying to prove Datto Device Visibility and API Component Level through GET-only calls that require additional read permissions the execution identity intentionally does not have.

## Live evidence already established

The separate `datto_rmm.execution` identity is staged in OpenBao, its AppRole lifecycle is proven, Datto OAuth authentication succeeds, the identity lacks Global Settings View, and no provider mutation or component execution has occurred.

A GET-only Device Visibility probe then used the existing read identity to resolve known valid endpoints and tested them through the execution identity. Two valid devices returned HTTP 403 for both the site and device reads; a third candidate did not resolve through the read identity. No mutation occurred and the result was correctly classified as inconclusive.

## Why the GET-only proof cannot isolate the controls

Datto's current API permission matrix requires `Sites > Devices: View` for `GET /v2/device/{deviceUid}` in addition to Device Visibility. The execution identity was intentionally designed around the minimum quick-job permission set, which uses `Sites > Devices: Manage` rather than adding broad read authority solely for testing. Therefore HTTP 403 on the device GET cannot distinguish Device Visibility denial from the absence of the separate Devices View permission.

Similarly, `GET /v2/account/components` requires Global Settings View in addition to Components View and API Component Level. Global Settings View has already been deliberately excluded and its absence proven. Therefore that endpoint cannot independently prove API Component Level without broadening the execution identity merely to make a test observable.

Datto documents both Device Visibility and API Component Level as restrictions on `PUT /v2/device/{deviceUid}/quickjob`. That operation is the meaningful end-to-end enforcement point.

## Decision

Do not grant extra Global Settings View or Devices View permissions merely to satisfy a proof harness. That would weaken the least-privilege design for the sake of testing.

Treat the owner-configured Device Visibility and API Component Level as provider-side configuration evidence sufficient to continue source-only implementation work. Record that independent runtime enforcement remains unproven until the first separately approved live pilot quick job.

Continue building and testing the governed runtime execution surface without production activation. Before the first live quick job, require explicit owner approval and reconfirm the intended pilot endpoint and approved component. The first governed pilot should then serve as the end-to-end proof that Device Visibility, API Component Level, exact component allowlisting, approval binding, execution credential isolation, provider mutation transport, job tracking, and audit behavior all work together.

## Security boundary

This strategy does not authorize runtime deployment, provider-write activation, or a live quick job. Production remains read-only. Separate explicit approval is still required before any live component execution.
