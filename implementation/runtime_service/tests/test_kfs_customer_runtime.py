"""Preproduction-only activation checks for AOT copier SharePoint enrichment."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jason_runtime.kfs_customer_runtime import (
    MANIFEST_SCHEMA,
    WORKLOAD_PRINCIPAL_ID,
    build_governed_copier_evidence_cache,
    load_approved_manifest,
    parse_approved_manifest,
)

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"


def approved_manifest():
    return {
        "schema": MANIFEST_SCHEMA,
        "organization_id": "aot",
        "principal_id": WORKLOAD_PRINCIPAL_ID,
        "microsoft_tenant_id": TENANT,
        "approved_sources": [
            {
                "site_id": "approved-admin-site",
                "drive_id": "approved-aot-document-library",
                "item_id": "approved-copier-meter-file",
            },
        ],
        "grant_expires_at": (NOW + timedelta(days=7)).isoformat(),
        "approval_reference": "https://github.com/al-teamaot-com/jason/issues/2176",
    }


def test_strict_manifest_uses_exact_source_identity():
    manifest = parse_approved_manifest(approved_manifest(), now=NOW)
    assert manifest.tenant_id == TENANT
    assert manifest.principal_id == WORKLOAD_PRINCIPAL_ID
    assert len(manifest.sources) == 1
    assert manifest.sources[0].item_id == "approved-copier-meter-file"


@pytest.mark.parametrize("field,value", [
    ("principal_id", "arbitrary-user"),
    ("organization_id", "other-org"),
    ("schema", "unknown"),
])
def test_document_manifest_rejects_unapproved_identity(field, value):
    payload = approved_manifest()
    payload[field] = value
    with pytest.raises(PermissionError, match="AOT-only|principal mismatch"):
        parse_approved_manifest(payload, now=NOW)


@pytest.mark.parametrize("selector", [
    {"site_id": "approved-admin-site", "drive_id": "approved-library", "item_id": "*"},
    {"site_id": "approved-admin-site", "drive_id": "approved-library", "item_id": "https://untrusted/file"},
    {"site_id": "approved-admin-site", "drive_id": "approved-library", "item_id": "abc?token=1"},
])
def test_reject_untrusted_sharepoint_selectors(selector):
    payload = approved_manifest()
    payload["approved_sources"] = [selector]
    with pytest.raises(ValueError, match="unsafe"):
        parse_approved_manifest(payload, now=NOW)


def test_unsupported_or_duplicate_manifest_fails_closed():
    payload = approved_manifest()
    payload["extra_permissions"] = "Files.ReadWrite.All"
    with pytest.raises(ValueError, match="exact approved"):
        parse_approved_manifest(payload, now=NOW)
    payload.pop("extra_permissions")
    payload["approved_sources"].append(dict(payload["approved_sources"][0]))
    with pytest.raises(ValueError, match="duplicates"):
        parse_approved_manifest(payload, now=NOW)


def test_expired_or_overlong_approval_cannot_be_loaded():
    payload = approved_manifest()
    payload["grant_expires_at"] = (NOW - timedelta(seconds=5)).isoformat()
    with pytest.raises(PermissionError, match="expired or unbounded"):
        parse_approved_manifest(payload, now=NOW)
    payload["grant_expires_at"] = (NOW + timedelta(days=100)).isoformat()
    with pytest.raises(PermissionError, match="expired or unbounded"):
        parse_approved_manifest(payload, now=NOW)


def test_local_manifest_symlink_and_writable_modes_rejected(tmp_path):
    path = tmp_path / "copier-evidence.json"
    path.write_text(json.dumps(approved_manifest()), encoding="utf-8")
    path.chmod(0o644)
    assert load_approved_manifest(path, now=NOW).sources
    path.chmod(0o666)
    with pytest.raises(PermissionError, match="permissions"):
        load_approved_manifest(path, now=NOW)
    path.chmod(0o600)
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(path)
    with pytest.raises(PermissionError, match="symlink"):
        load_approved_manifest(symlink, now=NOW)


def test_builder_fails_before_graph_import_without_dedicated_approle(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(approved_manifest()), encoding="utf-8")
    manifest_path.chmod(0o600)
    with pytest.raises(PermissionError, match="not provisioned"):
        build_governed_copier_evidence_cache(
            manifest_path=manifest_path,
            boundary_db=tmp_path / "boundaries.sqlite3",
            openbao_url="http://127.0.0.1:8200",
            role_id_path=tmp_path / "missing-approle-role-id",
            secret_id_path=tmp_path / "missing-approle-secret-id",
            transport=object(),
            audit=object(),
            now=NOW,
        )


def seed_approved_sharepoint_boundary(db_path):
    """Synthetic validated Entra consent record for combined preproduction QA."""
    from kernel.client_boundaries import (
        BoundaryStatus, ClientBoundary,
        SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore,
    )
    store = SQLiteClientBoundaryStore(db_path)
    try:
        repository = SQLiteClientBoundaryRepository(store)
        repository.add(ClientBoundary(
            id="synthetic-aot-sharepoint-consent",
            client_id="client-aot-internal",
            provider="microsoft_graph_sharepoint",
            external_tenant_id=TENANT,
            primary_domain="teamaot.com",
            profile="sharepoint-read",
            application_id="2cc50c39-39f6-481c-8065-73487623bcc9",
            status=BoundaryStatus.VALIDATED,
            consent_transaction_id="preproduction-fixture",
            created_at=NOW,
            consented_at=NOW,
            validated_at=NOW,
            service_principal_id="approved-synthetic-sharepoint-service",
        ))
    finally:
        store.close()


def test_enabled_builder_reuses_existing_governed_sharepoint_reader(tmp_path):
    """Only runs when both development PRs are present in the QA checkout."""
    pytest.importorskip("connectors.microsoft_graph.sharepoint_connector")
    from connectors.core.http_transport import UrlLibJsonHttpTransport
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(approved_manifest()), encoding="utf-8")
    manifest_path.chmod(0o600)
    role = tmp_path / "role_id"
    secret = tmp_path / "secret_id"
    role.write_text("synthetic-test-only-role", encoding="utf-8")
    secret.write_text("synthetic-test-only-secret", encoding="utf-8")
    role.chmod(0o600)
    secret.chmod(0o600)
    seed_approved_sharepoint_boundary(tmp_path / "boundaries.sqlite3")
    cache = build_governed_copier_evidence_cache(
        manifest_path=manifest_path,
        boundary_db=tmp_path / "boundaries.sqlite3",
        openbao_url="http://127.0.0.1:8200",
        role_id_path=role, secret_id_path=secret,
        transport=UrlLibJsonHttpTransport(),
        audit=object(),
        now=NOW,
    )
    assert cache._loader.principal_id == WORKLOAD_PRINCIPAL_ID
    connector = cache._loader.connector
    assert connector.organization_bindings is not None
    assert len(connector.authorizer.grants) == 1
    assert cache._authorization_expires_at == NOW + timedelta(days=7)
    assert connector.bindings.find_active_by_jason_identity(
        jason_identity_id="any-human"
    ) is None



def test_exact_aot_document_manifest_template_requires_activation_review():
    import json
    root = Path(__file__).resolve().parents[3]
    template = root / "config/preproduction/aot-kfs-copier-documents.example.json"
    payload = json.loads(template.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="valid bounded"):
        parse_approved_manifest(payload, now=NOW)
    payload["grant_expires_at"] = (NOW + timedelta(days=7)).isoformat()
    validated = parse_approved_manifest(payload, now=NOW)
    assert validated.tenant_id == TENANT
    assert len(validated.sources) == 3
    assert all(source.site_id.startswith("absolnet.sharepoint.com,") for source in validated.sources)


def test_runtime_configuration_has_default_off_and_kfs_dependency_gate():
    # Foundation CI deliberately avoids importing unrelated runtime adapters.
    # Full Jason runtime CI imports composition and executes its integration tests.
    source = (
        Path(__file__).resolve().parents[1] /
        "src/jason_runtime/composition.py"
    ).read_text(encoding="utf-8")
    assert "kfs_copier_evidence_enabled: bool = False" in source
    assert "JASON_KFS_COPIER_EVIDENCE_ENABLED" in source
    assert "if self.kfs_copier_evidence_enabled and not self.kfs_enabled:" in source
    assert "build_governed_copier_evidence_cache" in source
    assert "customer_evidence_resolver=copier_evidence_resolver" in source


def test_sharepoint_builder_rejects_unvalidated_tenant_even_with_role_files(tmp_path):
    """A document grant and synthetic AppRole files are not Entra consent."""
    pytest.importorskip("connectors.microsoft_graph.sharepoint_connector")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(approved_manifest()), encoding="utf-8")
    manifest_path.chmod(0o600)
    role = tmp_path / "role_id"
    secret = tmp_path / "secret_id"
    role.write_text("synthetic-role", encoding="utf-8")
    secret.write_text("synthetic-secret", encoding="utf-8")
    role.chmod(0o600)
    secret.chmod(0o600)
    with pytest.raises(PermissionError, match="Dedicated validated"):
        build_governed_copier_evidence_cache(
            manifest_path=manifest_path,
            boundary_db=tmp_path / "boundaries.sqlite3",
            openbao_url="http://127.0.0.1:8200",
            role_id_path=role, secret_id_path=secret,
            transport=object(), audit=object(), now=NOW,
        )
