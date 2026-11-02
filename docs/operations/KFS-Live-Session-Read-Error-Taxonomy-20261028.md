# KFS live session read: safe failure taxonomy

## Why this source patch is necessary

After the approved production deployment `b40c2f4a47e60e31e2241e4a4d55759242c2b580`, live `print.device.search` still returned `PROVIDER_TRANSPORT_FAILURE`. The prior status-preservation patch correctly handled KFS HTTP errors and numeric application errors, but other network and response parsing failures were still collapsed into the same generic result. Host and runtime-container DNS and TLS reachability were healthy; that does not establish that authenticated KFS API calls are succeeding.

The live runtime uses `connectors.kyocera_kfs.connector.KyoceraKfsConnector`, which is a compatibility alias for `KyoceraKfsSessionConnector`; its `client_factory` is `KyoceraKfsSessionClient`. The diagnostic patch therefore belongs in `implementation/connectors/kyocera_kfs/client.py`, **not** the old stateless request preparer.

## Bounded error codes

The live session client reuses the core HTTP transport's fixed, credential-free network taxonomy. It reports only:

- `KFS_NETWORK_TIMEOUT`, `KFS_DNS_RESOLUTION`, `KFS_TLS_FAILURE`, `KFS_CONNECTION_REFUSED`, `KFS_NETWORK_UNREACHABLE`, or `KFS_NETWORK_IO_FAILURE` for transport exceptions;
- `KFS_INVALID_JSON` or `KFS_INVALID_RESPONSE_SHAPE` for unusable API replies;
- the previously implemented `PROVIDER_HTTP_STATUS_<code>` for real HTTP errors and `KFS_APPLICATION_STATUS_<code>` for real numeric KFS business-status errors.

The response body, source exception message, headers, authorization, API gateway credential, Manager username/password, and operational request are **never** placed in the error code or rendered exception. Provider state is not mutated; no login credentials change or additional retries are introduced.

## Verification and next action

Local tests include every error class and an explicit runtime alias assertion, plus the existing successful read contract. Protected CI and isolated release preproduction remain required. After exact-SHA owner-approved deployment, rerun one governed `print.device.search` and use its bounded code to determine whether the blocker is provider auth, provider response, or a network/TLS problem. This patch does not claim to repair the underlying KFS endpoint and does not authorize a direct API bypass.
