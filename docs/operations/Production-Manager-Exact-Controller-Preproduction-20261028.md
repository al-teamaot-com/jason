# Production Manager P0: exact-controller preproduction acceptance

A release which changes `tools/release_manager_host_runner.py` cannot be certified by an older installed Production Manager. The older controller would run its own preproduction behavior, not the reviewed candidate behavior, and could mark the record `production_eligible` without the new required validation evidence.

Before transitioning to `preproduction`, the runner now reads the candidate controller bytes from the exact reviewed Git SHA and compares their digest with the currently executing controller file. The digest mismatch is a hard stop **before release-state mutation**. A missing or unverifiable candidate Git object is also a hard stop. This is independent of application release, rollback and provider permission checks.

For controller-changing releases, run preparation with the immutable candidate's exact source, using `--repo` pointed at that same SHA checkout. Do not install or overwrite the current production controller manually; native promotion and the host reconciler remain solely responsible for installing verified candidate code after acceptance. A historical record prepared by an older controller remains historical evidence and is not silently upgraded or accepted as evidence from the candidate controller.

The original production freeze and exact-source owner authorization remain in effect. Acceptance includes tests for both matching and mismatching controller Git bytes and confirmation that failure cannot advance the release state. No change here grants access to Autotask, Datto, IT Glue or any user-disruptive operation.
