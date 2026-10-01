# Jason Exchange Online Read Worker

Internal execution worker for CAP-003 Microsoft 365 mail investigations.

## Security boundary

This container is not a general PowerShell execution service.

It accepts only the fixed operations implemented in `invoke_exchange_read.ps1`. The request schema contains no script, cmdlet, pipeline, file, or arbitrary PowerShell field.

The worker:

- uses app-only certificate authentication;
- connects only to a validated primary `.onmicrosoft.com` organization supplied by the governed Jason client boundary;
- imports only the read cmdlets named by `Connect-ExchangeOnline -CommandName`;
- returns normalized JSON;
- is intended to have no host-published port;
- requires an internal bearer token in addition to Docker-network isolation.

## Runtime secrets

Mount read-only:

- `/run/jason-secrets/microsoft-exchange/certificate.pfx`
- `/run/jason-secrets/microsoft-exchange/certificate-password`
- `/run/jason-secrets/microsoft-exchange/worker-token`

Non-secret:

- `JASON_EXCHANGE_APP_ID`

The PFX is an implementation bridge for Exchange Online PowerShell. The long-term credential source remains the approved Jason secret boundary; production deployment should materialize the PFX into a short-lived read-only runtime mount and never persist it in the repository or image.

## Module version

The image pins ExchangeOnlineManagement 3.10.1. Version changes require automated tests and an AOT acceptance run before production promotion.
