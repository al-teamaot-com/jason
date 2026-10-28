# Native Autotask v13 preflight allowlist correction — 2026-10-28

## Observed dry-run failure

The candidate SHA `cb15c995f6745d2ed93df1044f2fe258918d6175`
passed 13 GitHub checks and its source tests. Native preparation created
immutable candidate images and a **temporary isolated preproduction
container**, but failed with exit code 2 at the
`infrastructure/jason-runtime/production-deploy.sh --preflight`
stage.

Source inspection proved both production deployment shells still
accepted only `v10` and `v11` read profiles in their local,
source-bound JSON allowlist. The v13 config was therefore rejected
without production mutation. The prior release record remains
`release_candidate` and is **not eligible for promotion**.

## Minimal correction

Both original production scripts now accept the explicit reviewed
`itglue-autotask-entra-dynamic-schema-read-catalog-v13` profile in the
same existing fail-closed source manifest check. The independent native
controller and runtime/source profiles already support v13.

Nothing is loosened: the script still requires the exact three-key
immutable profile pair, version `1.0`, the exact candidate and
rollback override values (when passed), and both pre-existing live
containers reporting the exact declared **v10** rollback profile
before forward activation. Native rollback still strips the candidate
profile and restores **v10** via the exact
`JASON_PROVIDER_READ_ROLLBACK_PROFILE` source declaration.

Both source-shell preflights are tested with actual extracted shell
code and **fake Docker**, including forward v13, legacy manager
preflight without overrides, rollback after v13, mismatched source,
wrong live baseline, wrong rollback, and unrelated profiles. The
existing CI dynamic schema workflow now triggers on both production
scripts and runs their preflight tests on protected pull requests.

## Production control

This source fix produces a **new SHA**. No approval for the earlier
`cb15c995...` may be reused for its successor. Run new exact-SHA
native preparation, source/parallel-work review, rollback verification,
CCC and authenticated same-human ticket/Projects/ActionTypes canary
before production close. Owner standing all-promotion freeze remains
active unless a new exact-SHA one-time exception is recorded.

No production runtime, MCP, provider API, network, or customer data
has been modified as part of this source correction.
