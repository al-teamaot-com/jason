from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kernel.identity_authority.contracts import PermissionMode
from kernel.identity_authority.delegation import (
    DelegationRecord,
    DelegationValidationRequest,
    DelegationValidator,
)


class Repo:
    def __init__(self, record):
        self.record = record

    def get_delegation(self, delegation_id):
        if self.record is not None and self.record.delegation_id == delegation_id:
            return self.record
        return None


def record(now):
    return DelegationRecord(
        delegation_id="del-1",
        delegator_id="person-al",
        delegate_id="svc-openclaw-gateway",
        organization_id="aot",
        client_id="client-1",
        capability="autotask.ticket.get",
        maximum_mode=PermissionMode.OBSERVE,
        effective_from=now - timedelta(minutes=1),
        effective_until=now + timedelta(minutes=5),
    )


def request(**overrides):
    values = dict(
        delegation_id="del-1",
        delegator_id="person-al",
        delegate_id="svc-openclaw-gateway",
        organization_id="aot",
        client_id="client-1",
        capability="autotask.ticket.get",
        requested_mode=PermissionMode.OBSERVE,
    )
    values.update(overrides)
    return DelegationValidationRequest(**values)


def test_valid_delegation_allows_exact_scope():
    now = datetime.now(timezone.utc)
    validator = DelegationValidator(Repo(record(now)), clock=lambda: now)
    result = validator.validate(request())
    assert result.valid is True
    assert result.reason_code == "DELEGATION_VALID"


def test_delegation_rejects_other_principal_or_service():
    now = datetime.now(timezone.utc)
    validator = DelegationValidator(Repo(record(now)), clock=lambda: now)
    assert validator.validate(request(delegator_id="person-other")).reason_code == "DELEGATION_SCOPE_MISMATCH"
    assert validator.validate(request(delegate_id="svc-other")).reason_code == "DELEGATION_SCOPE_MISMATCH"


def test_delegation_rejects_broader_mode():
    now = datetime.now(timezone.utc)
    validator = DelegationValidator(Repo(record(now)), clock=lambda: now)
    result = validator.validate(request(requested_mode=PermissionMode.EXECUTE))
    assert result.valid is False
    assert result.reason_code == "DELEGATION_MODE_EXCEEDED"


def test_delegation_rejects_expired_record():
    now = datetime.now(timezone.utc)
    expired = record(now)
    expired = DelegationRecord(
        delegation_id=expired.delegation_id,
        delegator_id=expired.delegator_id,
        delegate_id=expired.delegate_id,
        organization_id=expired.organization_id,
        client_id=expired.client_id,
        capability=expired.capability,
        maximum_mode=expired.maximum_mode,
        effective_from=now - timedelta(minutes=10),
        effective_until=now - timedelta(minutes=1),
    )
    validator = DelegationValidator(Repo(expired), clock=lambda: now)
    result = validator.validate(request())
    assert result.valid is False
    assert result.reason_code == "DELEGATION_NOT_EFFECTIVE"
