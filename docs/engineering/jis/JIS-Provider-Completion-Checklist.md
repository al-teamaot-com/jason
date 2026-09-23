# JIS Provider Completion Checklist

## Discovery

- [ ] Business requirement is documented.
- [ ] Official provider API documentation was reviewed.
- [ ] Existing Jason and approved open-source capabilities were evaluated.
- [ ] Scope and exclusions are documented.
- [ ] Provider owner and Technology Steward are named.

## Foundation

- [ ] Provider package exists.
- [ ] Connector inherits the shared JIS lifecycle where appropriate.
- [ ] Provider name is registered.
- [ ] Named capabilities are registered.
- [ ] Provider-specific behavior is isolated.

## Secrets and Identity

- [ ] Logical secret contract exists.
- [ ] OpenBao path follows the approved layout.
- [ ] Approved secret fields are minimal.
- [ ] Least-privilege provider identity exists.
- [ ] Least-privilege AppRole or service identity exists.
- [ ] Bootstrap files are root-owned and private.
- [ ] Rotation and expiration requirements are documented.
- [ ] Read and write identities are separated where practical.

## Operations

- [ ] Operation registry exists where appropriate.
- [ ] Required arguments are validated.
- [ ] Optional arguments are handled explicitly.
- [ ] Unknown operations fail closed.
- [ ] Arbitrary provider paths cannot be constructed.

## Generic Entity Gateway

- [ ] Generic gateway exists where supported.
- [ ] Approved entity allow-list exists.
- [ ] Unapproved entities fail closed.
- [ ] Provider-specific exceptions are documented.
- [ ] Sensitive resources are excluded unless explicitly approved.

## Mutations

- [ ] Read access does not imply write authority.
- [ ] Mutation policies exist.
- [ ] Business reason is required where applicable.
- [ ] Approval is bound to the planned arguments.
- [ ] Idempotency is defined.
- [ ] Current state is revalidated.
- [ ] Result verification is defined.
- [ ] Rollback or compensating action is documented.

## Testing

- [ ] Focused provider tests pass.
- [ ] Shared JIS tests pass.
- [ ] Full regression tests pass.
- [ ] Authorization failures are tested.
- [ ] Secret-safety failures are tested.
- [ ] Invalid arguments are tested.
- [ ] Provider errors are handled safely.
- [ ] Tests contain no production credentials or sensitive client data.

## Production Validation

- [ ] Authentication succeeds.
- [ ] Least-privilege permissions are confirmed.
- [ ] A known record was retrieved.
- [ ] A query or collection operation was tested.
- [ ] Failure handling was observed.
- [ ] Secrets were not displayed or logged.
- [ ] Validation evidence was recorded safely.

## Interfaces

- [ ] CLI uses the provider through JIS.
- [ ] Platform API uses the provider through JIS.
- [ ] Other interfaces do not call the provider directly.
- [ ] Human-readable output exists where useful.
- [ ] Machine-readable output exists where useful.

## Documentation

- [ ] Provider specification exists.
- [ ] Secret contract is documented.
- [ ] Capability catalog is updated.
- [ ] Connector catalog is updated.
- [ ] Operational runbooks are updated.
- [ ] Known limitations are documented.
- [ ] Provider Development Guide was reviewed.

## Closeout

- [ ] Pull requests are merged.
- [ ] Temporary branches are removed.
- [ ] Repository is clean.
- [ ] Architecture review is complete.
- [ ] Required ADRs exist.
- [ ] Milestone closeout is complete.
