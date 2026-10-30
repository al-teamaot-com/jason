"""Fail-closed runtime wiring for approved AOT copier document evidence.

This module uses the reusable governed SharePoint connector (PR #1330) and
the KFS source loader (PR #2177). It never uses delegated ChatGPT credentials
or accepts document selectors from user messages. Source manifest and separate
SharePoint AppRole credentials are required; the feature defaults to disabled.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from .kfs_customer_document_source import (
    ApprovedAotCopierSource,
    GovernedAotCopierEvidenceCache,
    GovernedAotCopierSourceLoader,
)


WORKLOAD_PRINCIPAL_ID = "jason-kfs-evidence-service"
MANIFEST_SCHEMA = "aot-kfs-copier-document-sources/v1"


@dataclass(frozen=True, slots=True)
class ValidatedAotCopierManifest:
    tenant_id: str
    principal_id: str
    sources: tuple[ApprovedAotCopierSource, ...]
    grant_expires_at: datetime


def parse_approved_manifest(payload: Mapping[str, Any], *, now: datetime) -> ValidatedAotCopierManifest:
    if now.tzinfo is None:
        raise ValueError("manifest time must be timezone aware")
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema", "organization_id", "principal_id", "microsoft_tenant_id",
        "approved_sources", "grant_expires_at", "approval_reference",
    }:
        raise ValueError("exact approved copier-source manifest schema required")
    if payload["schema"] != MANIFEST_SCHEMA or payload["organization_id"] != "aot":
        raise PermissionError("document manifest must be AOT-only")
    if payload["principal_id"] != WORKLOAD_PRINCIPAL_ID:
        raise PermissionError("approved copier workload principal mismatch")
    try:
        tenant_id = str(UUID(payload["microsoft_tenant_id"]))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("validated Microsoft tenant UUID required") from exc
    reference = payload["approval_reference"]
    if not isinstance(reference, str) or not reference.startswith(
        "https://github.com/al-teamaot-com/jason/issues/"
    ):
        raise PermissionError("owner-approved AOT document scope reference required")
    sources_data = payload["approved_sources"]
    if not isinstance(sources_data, list) or not 1 <= len(sources_data) <= 40:
        raise ValueError("one to 40 explicit approved document selectors required")
    sources = []
    for item in sources_data:
        if not isinstance(item, dict) or set(item) != {"site_id", "drive_id", "item_id"}:
            raise ValueError("exact site/drive/item selectors required")
        fields = [item["site_id"], item["drive_id"], item["item_id"]]
        if any(
            not isinstance(value, str)
            or not value.strip() or value.strip() != value or value == "*" or len(value) > 512
            or any(char in value for char in ("/", "?", "#", "\\", "%", "\r", "\n"))
            for value in fields
        ):
            raise ValueError("unsafe or nonexact SharePoint document selector")
        sources.append(ApprovedAotCopierSource(
            tenant_id=tenant_id, site_id=item["site_id"],
            drive_id=item["drive_id"], item_id=item["item_id"],
        ))
    try:
        expires = datetime.fromisoformat(
            payload["grant_expires_at"].replace("Z", "+00:00")
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("valid bounded document authorization expiration required") from exc
    if expires.tzinfo is None or not now < expires <= now + timedelta(days=30):
        raise PermissionError("copier source grant is expired or unbounded")
    if len({(source.site_id, source.drive_id, source.item_id) for source in sources}) != len(sources):
        raise ValueError("approved copier source contains duplicates")
    return ValidatedAotCopierManifest(
        tenant_id=tenant_id, principal_id=WORKLOAD_PRINCIPAL_ID,
        sources=tuple(sources), grant_expires_at=expires,
    )


def load_approved_manifest(path: Path, *, now: datetime) -> ValidatedAotCopierManifest:
    """Refuse untrusted, symlink, group-writable or oversized local manifests."""
    if path.is_symlink():
        raise PermissionError("approved document source manifest must not be a symlink")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise PermissionError("approved source manifest must be a regular file")
    if info.st_size > 32 * 1024 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise PermissionError("approved source manifest has unsafe size or permissions")
    if info.st_uid not in {0, os.getuid()}:
        raise PermissionError("approved source manifest has untrusted owner")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_approved_manifest(raw, now=now)


@dataclass(frozen=True, slots=True)
class AotServiceBinding:
    status: str
    organization_id: str
    jason_identity_id: str
    microsoft_tenant_id: str
    profile: str


@dataclass(frozen=True, slots=True)
class AotServiceBindings:
    bound: AotServiceBinding

    def find_active_by_jason_service_identity(self, *, jason_identity_id: str, organization_id: str):
        if jason_identity_id != self.bound.jason_identity_id or organization_id != "aot":
            return None
        return self.bound


class DenyClientBoundSharePointIdentities:
    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        return None


def build_governed_copier_evidence_cache(
    *,
    manifest_path: Path,
    boundary_db: Path,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: Any,
    audit: Any,
    now: datetime | None = None,
) -> GovernedAotCopierEvidenceCache:
    """Construct only from the existing dedicated SharePoint profile.

    The caller MUST enable this explicitly via a trusted runtime configuration.
    This returns a lazy cache, not a new public connector capability. It refuses
    to initialize without separate role/secret file references.
    """
    now = now or datetime.now(timezone.utc)
    manifest = load_approved_manifest(manifest_path, now=now)
    if (
        not role_id_path.is_file() or not secret_id_path.is_file()
        or role_id_path.is_symlink() or secret_id_path.is_symlink()
    ):
        raise PermissionError("dedicated SharePoint AppRole credential is not provisioned")

    # These imports exist only after the separate governed SharePoint PR is
    # reviewed and integrated. Default-off KFS runtime needs no SharePoint import.
    from connectors.microsoft_graph.aot_document_policy import (
        ApprovedAotDocumentGrant, AotExactDocumentReleasePolicy,
        DOCUMENT_READ_OPERATIONS,
    )
    from connectors.microsoft_graph.sharepoint_connector import GovernedSharePointConnector
    from .microsoft_sharepoint import build_microsoft_sharepoint_runtime

    runtime = build_microsoft_sharepoint_runtime(
        boundary_db=boundary_db, openbao_url=openbao_url,
        role_id_path=role_id_path, secret_id_path=secret_id_path,
        transport=transport,
    )
    binding = AotServiceBinding(
        status="active", organization_id="aot",
        jason_identity_id=manifest.principal_id,
        microsoft_tenant_id=manifest.tenant_id,
        profile="aot-approved-document-read",
    )
    grants = frozenset(
        ApprovedAotDocumentGrant(
            principal_id=manifest.principal_id,
            microsoft_tenant_id=manifest.tenant_id,
            site_id=source.site_id, drive_id=source.drive_id,
            item_id=source.item_id,
            operations=DOCUMENT_READ_OPERATIONS,
            expires_at=manifest.grant_expires_at,
        )
        for source in manifest.sources
    )
    connector = GovernedSharePointConnector(
        reader=runtime.reader,
        bindings=DenyClientBoundSharePointIdentities(),
        authorizer=AotExactDocumentReleasePolicy(grants),
        audit=audit,
        organization_bindings=AotServiceBindings(binding),
    )
    loader = GovernedAotCopierSourceLoader(
        connector=connector,
        principal_id=manifest.principal_id,
        sources=manifest.sources,
    )
    return GovernedAotCopierEvidenceCache(
        loader=loader, max_age_hours=24,
        authorization_expires_at=manifest.grant_expires_at,
    )
