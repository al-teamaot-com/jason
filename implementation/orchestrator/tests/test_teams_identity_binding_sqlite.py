from __future__ import annotations

import stat

from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore


def binding(status="active"):
    return MicrosoftIdentityBinding(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        jason_identity_id="person-al",
        client_id=None,
        status=status,
    )


def test_store_is_owner_only_and_requires_explicit_binding(tmp_path):
    path = tmp_path / "teams" / "identity-bindings.sqlite3"
    store = SQLiteMicrosoftIdentityBindingStore(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.find(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    ) is None

    store.put(binding())
    stored = store.find(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    )
    assert stored == binding()


def test_binding_update_is_explicit_and_can_revoke(tmp_path):
    store = SQLiteMicrosoftIdentityBindingStore(tmp_path / "bindings.sqlite3")
    store.put(binding())
    store.put(binding(status="revoked"))

    stored = store.find(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    )
    assert stored is not None
    assert stored.status == "revoked"
