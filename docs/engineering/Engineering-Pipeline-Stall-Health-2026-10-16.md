# Engineering pipeline stall health

A pipeline stage returning zero is not proof of progress. When approved work is outstanding and no workers are active despite available capacity, the pipeline marks health degraded and exits nonzero for supervision. It does not automatically retry an exhausted reasoning request or grant additional execution authority.

Transport failures are classified into bounded non-secret categories such as DNS resolution, connection refused, timeout, TLS failure, and unreachable network. These diagnostics must never include raw connection exception contents, endpoint URLs, credentials, or headers.

Operators must still repair the underlying failure and re-admit work through existing governed processes. Deploy only through protected CI, independent review, CCC and Release Manager verification.
