from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from tools import sharepoint_boundary_bootstrap as bootstrap
from kernel.client_boundaries import (
    BoundaryStatus, SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore,
)


def _token(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return "header." + payload + ".signature"


def test_token_claims_validate_exact_app_tenant_principal_and_role():
    claims = {
        "tid": "11111111-1111-1111-1111-111111111111",
        "appid": "22222222-2222-2222-2222-222222222222",
        "oid": "33333333-3333-3333-3333-333333333333",
        "roles": ["Sites.Read.All"],
    }
    parsed = bootstrap.token_claims(_token(claims))
    bootstrap.validate_claims(
        parsed,
        tenant=claims["tid"],
        app=claims["appid"],
        service_principal=claims["oid"],
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("tid", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        ("appid", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        ("oid", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        ("roles", ["User.Read.All"]),
    ],
)
def test_token_claims_reject_wrong_identity_or_missing_role(field, value):
    claims = {
        "tid": "11111111-1111-1111-1111-111111111111",
        "appid": "22222222-2222-2222-2222-222222222222",
        "oid": "33333333-3333-3333-3333-333333333333",
        "roles": ["Sites.Read.All"],
    }
    claims[field] = value
    with pytest.raises(bootstrap.BootstrapDenied):
        bootstrap.validate_claims(
            claims,
            tenant="11111111-1111-1111-1111-111111111111",
            app="22222222-2222-2222-2222-222222222222",
            service_principal="33333333-3333-3333-3333-333333333333",
        )


def test_persist_creates_validated_boundary_through_onboarding_services(tmp_path, monkeypatch):
    db = tmp_path / "boundaries.sqlite3"
    db.touch(mode=0o600)
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    result = bootstrap._persist(
        db_path=db,
        tenant="11111111-1111-1111-1111-111111111111",
        app="22222222-2222-2222-2222-222222222222",
        service_principal="33333333-3333-3333-3333-333333333333",
        domain="teamaot.com",
        client="client-aot-internal",
        approval_reference=bootstrap.APPROVAL_SCOPE,
    )
    assert result == "created_and_validated"
    store = SQLiteClientBoundaryStore(db)
    boundary = SQLiteClientBoundaryRepository(store).find_active_for_client(
        client_id="client-aot-internal", provider=bootstrap.PROVIDER
    )
    assert boundary is not None
    assert boundary.status is BoundaryStatus.VALIDATED
    assert boundary.application_id == "22222222-2222-2222-2222-222222222222"
    assert boundary.service_principal_id == "33333333-3333-3333-3333-333333333333"
    assert boundary.validated_at is not None
    store.close()


def test_persist_is_idempotent_for_same_validated_binding(tmp_path, monkeypatch):
    db = tmp_path / "boundaries.sqlite3"
    db.touch(mode=0o600)
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    arguments = dict(
        db_path=db,
        tenant="11111111-1111-1111-1111-111111111111",
        app="22222222-2222-2222-2222-222222222222",
        service_principal="33333333-3333-3333-3333-333333333333",
        domain="teamaot.com",
        client="client-aot-internal",
        approval_reference=bootstrap.APPROVAL_SCOPE,
    )
    assert bootstrap._persist(**arguments) == "created_and_validated"
    assert bootstrap._persist(**arguments) == "already_validated"


def test_persist_refuses_an_unapproved_scope(tmp_path, monkeypatch):
    db = tmp_path / "boundaries.sqlite3"
    db.touch(mode=0o600)
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    with pytest.raises(bootstrap.BootstrapDenied, match="EXACT_SHAREPOINT"):
        bootstrap._persist(
            db_path=db,
            tenant="11111111-1111-1111-1111-111111111111",
            app="22222222-2222-2222-2222-222222222222",
            service_principal="33333333-3333-3333-3333-333333333333",
            domain="teamaot.com",
            client="client-aot-internal",
            approval_reference="unrelated-scope",
        )
