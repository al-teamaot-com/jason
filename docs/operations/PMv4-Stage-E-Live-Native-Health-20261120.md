# Stage E live native preflight consistency

A historical component acceptance receipt does not establish current runtime health. Pre-approval checks must measure the same protected-component conditions as the final native controller.

The gate now performs read-only inspection of exactly the original controller's protected component set and applies its existing snapshot validator. Missing, malformed, stopped, starting or unhealthy state denies admission before an Owner decision. Historical receipts and application liveness responses cannot override this check. The native controller retains its independent under-lock revalidation.

The bootstrap retains bounded, syntactically safe native denial codes when promotion and recovery do not produce a matching receipt. Arbitrary stderr text is not propagated. Existing signed receipt, expiry, replay, recovery and freeze requirements remain intact.

Installer continuation remains pinned to one exact reviewed source/policy before-image and independently verifies its historical signed bootstrap evidence. Any native receipt for that installation still requires original ledger recovery. Historical evidence supplies no new release authority.

Regression coverage includes unhealthy/starting/missing state, malformed inspection responses, the exact read-only command set, and safe native error retention. Disposable UID0 tests also construct the production-mode native host and controller using original generic modules at canonical fixture paths. External operations use synthetic observations; these tests do not establish live acceptance.

Operational incident observations and identifiers are retained in private engineering evidence. Production recovery and promotion remain separately governed.
