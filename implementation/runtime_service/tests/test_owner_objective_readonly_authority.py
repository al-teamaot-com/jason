"""The isolated approver reads current Core authority without modifying it."""
from pathlib import Path
import sqlite3

import pytest

from kernel.identity_authority import (
    AuthorityGrant, IdentityRecord, PermissionMode, SQLiteIdentityAuthorityStore,
)
from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore


def test_readonly_authority_observes_current_revocation_and_cannot_write(tmp_path):
    path = tmp_path / "authority.db"
    writer = SQLiteIdentityAuthorityStore(path)
    record = IdentityRecord("existing-owner", "human", "aot")
    writer.put_identity(record)
    grant = AuthorityGrant("existing-grant", "existing-owner", "test.read",
                           "aot", None, PermissionMode.EXECUTE)
    writer.put_grant(grant)
    reader = SQLiteIdentityAuthorityStore(path, read_only=True)
    assert reader.get_identity("existing-owner") == record
    assert reader.get_grant("existing-grant").status == "active"
    writer.revoke_grant("existing-grant")
    assert reader.get_grant("existing-grant").status == "revoked"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        reader.put_identity(IdentityRecord("new-owner", "human", "aot"))
    assert writer.get_identity("new-owner") is None
    reader.close(); writer.close()


def test_readonly_binding_reader_cannot_enroll_or_change_owner(tmp_path):
    path = tmp_path / "bindings.db"
    writer = SQLiteMicrosoftIdentityBindingStore(path)
    original = MicrosoftIdentityBinding("aot-tenant", "existing-owner-oid", "existing-owner")
    writer.put(original)
    reader = SQLiteMicrosoftIdentityBindingStore(path, read_only=True)
    assert reader.find(microsoft_tenant_id="aot-tenant", microsoft_object_id="existing-owner-oid") == original
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        reader.put(MicrosoftIdentityBinding("aot-tenant", "forged-owner-oid", "existing-owner"))
    assert writer.find(microsoft_tenant_id="aot-tenant", microsoft_object_id="forged-owner-oid") is None


@pytest.mark.parametrize("store", [SQLiteIdentityAuthorityStore, SQLiteMicrosoftIdentityBindingStore])
def test_readonly_missing_source_never_creates_directory_or_database(tmp_path, store):
    path = tmp_path / "missing" / "source.db"
    with pytest.raises(sqlite3.OperationalError):
        store(path, read_only=True)
    assert not path.parent.exists()
