# Recover missing production last-known-good baseline

Use the release-manager `recover-baseline --revision <exact-sha> --owner-approved` command only when the circuit breaker is open, the baseline is missing, the exact historical release is closed and production-verified, current watchdog desired-state drift is `pass`, and the live production manifest independently validates the same SHA. Do not construct state files manually or close the breaker if active drift remains. The operation must fail closed.
