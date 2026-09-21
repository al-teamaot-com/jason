# Kyocera Fleet Services connector

This package implements Jason's governed, read-only Kyocera Fleet Services (KFS)
connector foundation.

## Why the API contract is configuration-driven

Kyocera publicly documents that KFS exposes an API for external ERP/SMS
integration, and Kyocera's U.S. integration request provides the API host and
dealer credential fields. The detailed dealer endpoint/header contract is not
published publicly.

Jason therefore does **not** guess endpoint paths or authentication header names.
The connector remains fail-closed until AOT receives the official Kyocera KFS API
integration package.

## Logical secret

`kyocera_kfs.readonly`

Required values:

- `access_id`
- `access_password`
- `request_from`
- `request_to`
- `authorization`
- `kfs_username`
- `kfs_password`
- `headers_json`
- `operations_json`

Optional:

- `api_url` (defaults to `https://api.kyods.com`; no other host is accepted)

`headers_json` is a JSON object whose values may reference the credential
fields above, for example:

```json
{
  "X-Provider-Access": "{access_id}",
  "Authorization": "{authorization}"
}
```

The example header names above are illustrative only. Use the exact names from
Kyocera's dealer API documentation.

`operations_json` defines the provider contract without changing code:

```json
{
  "device_search": {
    "method": "GET",
    "path": "/official/path/from/kyocera",
    "params": {
      "serial": "{serial_number}"
    }
  }
}
```

Supported operation keys:

- `device_search`
- `device_get`
- `meters_get`
- `supplies_get`
- `alerts_list`

Only GET and POST are accepted by this read-only connector. Paths must stay
local to `api.kyods.com`; external URLs and path traversal are rejected.

## Provider capabilities

- `kyocera_kfs.device.search`
- `kyocera_kfs.device.get`
- `kyocera_kfs.meters.get`
- `kyocera_kfs.supplies.get`
- `kyocera_kfs.alerts.list`

No KFS write or remote-management operation is enabled by this foundation.
