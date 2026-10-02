# Jason Exchange Online Read Worker

Internal execution worker for CAP-003 Microsoft 365 mail investigations.

## Security boundary

This container is not a general PowerShell execution service.

It accepts only the fixed operations implemented in `invoke_exchange_read.ps1`. The request schema contains no script, cmdlet, pipeline, file, or arbitrary PowerShell field.

The worker:

- receives a short-lived tenant-specific Exchange Online access token minted by Jason's governed MSAL/OpenBao identity layer;
- never receives the application certificate or private key;
- connects only to a validated primary `.onmicrosoft.com` organization supplied by the governed Jason client boundary;
- imports only the read cmdlets named by `Connect-ExchangeOnline -CommandName`;
- returns normalized JSON;
- is intended to have no host-published port;
- requires an internal bearer token in addition to Docker-network isolation;
- never logs the Exchange access token or request body.

## Runtime secret

Mount read-only:

- `/run/jason-secrets/microsoft-exchange/worker-token`

The Microsoft certificate credential remains in the approved Jason/OpenBao credential boundary. Jason exchanges it for a short-lived Exchange Online token and sends only that token to the worker for the immediate request.

## Module version

The image pins ExchangeOnlineManagement 3.10.1. Version changes require automated tests and an AOT acceptance run before production promotion.
