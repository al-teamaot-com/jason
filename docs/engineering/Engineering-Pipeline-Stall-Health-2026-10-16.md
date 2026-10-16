# Engineering pipeline stall health

A pipeline stage returning zero is not proof of progress. When approved work is outstanding and no workers are active despite available capacity, the pipeline marks health degraded and exits nonzero for supervision. It does not automatically retry an exhausted reasoning request or grant additional execution authority.

Transport failures are classified into bounded non-secret categories such as DNS resolution, connection refused, timeout, TLS failure, and unreachable network. These diagnostics must never include raw connection exception contents, endpoint URLs, credentials, or headers.

Operators must still repair the underlying failure and re-admit work through existing governed processes. Deploy only through protected CI, independent review, CCC and Release Manager verification.

## Native ownership of an existing approved implementation

The owner-approved development worker now accepts exactly one `Development pull
request: #number` selection in an already Owner-authored and approved issue. It
verifies same-repository source, target main, immutable head identity and actual
PR state. A stale reasoning failure can then be replaced by the real implementation
and CI stage without resetting retry counters or replaying old model requests.
Prior blocked-request and retry evidence is retained. Drafts are monitored, not
reported production-ready. Green checks mean awaiting governed integration, never
production success. Existing active editors are not preempted and this adoption
path does not mutate source or grant review/deployment authority.

The versioned `config/owner-approved-development-focus.json` restricts admission of
new discretionary development to #1440 and its specifically authorized blockers
#1493/#1458. Existing active engineering can reach a safe checkpoint; critical
support remains under its existing separate priority lane. This implements the
Owner's sole-priority instruction without creating another worker or dashboard.
