from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kernel.identity_authority import (
    DelegationRecord,
    DelegationValidationRequest,
    DelegationValidator,
    PermissionMode,
    SQLiteDelegationRepository,
    SQLiteIdentityAuthorityStore,
)


def test_delegation_persists_validates_and_revokes(tmp_path):
    now = datetime.now(timezone.utc)
    store = SQLiteIdentityAuthorityStore(tmp_path / "authority.sqlite3")
    repo = SQLiteDelegationRepository(store)
    try:
        repo.put(
            DelegationRecord(
                delegation_id="dlg-1",
                delegator_id="person-al",
                delegate_id="svc-openclaw-gateway",
                organization_id="aot",
                client_id="client-1",
                capability="autotask.ticket.get",
                maximum_mode=PermissionMode.OBSERVE,
                effective_from=now - timedelta(minutes=1),
                effective_until=now + timedelta(hours=1),
            )
        )

        validator = DelegationValidator(repo, clock=lambda: now)
        request = DelegationValidationRequest(
            delegation_id="dlg-1",
            delegator_id="person-al",
            delegate_id="svc-openclaw-gateway",
            organization_id="aot",
            client_id="client-1",
            capability="autotask.ticket.get",
            requested_mode=PermissionMode.OBSERVE,
        )
        assert validator.validate(request).valid is True

        assert repo.revoke(
            "dlg-1",
            revoked_at=now,
            reason="operator revoked delegation",
        ) is True
        result = validator.validate(request)
        assert result.valid is False
        assert result.reason_code == "DELEGATION_INACTIVE"
    finally:
        store.close()


def test_delegation_mode_and_scope_fail_closed(tmp_path):
    now = datetime.now(timezone.utc)
    store = SQLiteIdentityAuthorityStore(tmp_path / "authority.sqlite3")
    repo = SQLiteDelegationRepository(store)
    try:
        repo.put(
            DelegationRecord(
                delegation_id="dlg-1",
                delegator_id="person-al",
                delegate_id="svc-openclaw-gateway",
                organization_id="aot",
                client_id="client-1",
                capability="autotask.ticket.get",
                maximum_mode=PermissionMode.OBSERVE,
                effective_from=now - timedelta(minutes=1),
                effective_until=now + timedelta(hours=1),
            )
        )
        validator = DelegationValidator(repo, clock=lambda: now)

        over_mode = validator.validate(
            DelegationValidationRequest(
                "dlg-1", "person-al", "svc-openclaw-gateway", "aot",
                "client-1", "autotask.ticket.get", PermissionMode.EXECUTE,
            )
        )
        assert over_mode.reason_code == "DELEGATION_MODE_EXCEEDED"

        wrong_client = validator.validate(
            DelegationValidationRequest(
                "dlg-1", "person-al", "svc-openclaw-gateway", "aot",
                "client-2", "autotask.ticket.get", PermissionMode.OBSERVE,
            )
        )
        assert wrong_client.reason_code == "DELEGATION_SCOPE_MISMATCH"
    finally:
        store.close()
