# KFS governed read failure diagnostics — October 28, 2026

## Confirmed behavior

Jason's KFS `print.device.search` returned `PROVIDER_TRANSPORT_FAILURE` even with a bounded selector. Both the Jason host and the runtime container resolved the approved `api.kyods.com` hostname and established TLS 1.3 successfully. This establishes **network reachability only**; it does not prove KFS Manager login, dealer API authorization, business-status success, or active device enumeration.

The KFS read client discarded HTTP error codes and threw a generic `ConnectorTransportError`, making authentication, throttling and gateway failures indistinguishable in the governed response. It also folded unsuccessful KFS application `status.code` into the same generic error.

## Safe error classification

- HTTP failures retain only the numeric HTTP code and `kyocera_kfs` service tag, producing `PROVIDER_HTTP_STATUS_<code>` from the existing connector error contract.
- KFS JSON application failures retain only a *bounded numeric* `KFS_APPLICATION_STATUS_<code>` code; HTTP status and application status are never confused. Unknown/non-numeric application codes produce `KFS_APPLICATION_STATUS_UNKNOWN`.
- Provider HTTP response bodies, headers, error text, gateway Authorization, and KFS Manager password are never logged or included in exception messages.
- Read-only and AOT-internal organization boundary remain unchanged; login and meter acquisition algorithms are not changed. No retries of POST are introduced, to avoid repeating an uncertain provider operation without evidence.

## Acceptance and next step

Local tests assert numeric error codes, secret-free exception text, preserved success behavior and existing safe provider classification. After a separately authorized production deployment, retry one governed KFS device read. If the result indicates HTTP 401/403 or a KFS application credential failure, verify/rotate the dedicated KFS API gateway or Manager identity via approved secret-management processes. If HTTP 429, honor provider limits; if HTTP 5xx, investigate KFS service-side health. Never switch to portal scraping, direct credential calls or estimated meter readings.
