"""Provider-neutral artifact and evidence storage contracts for Project Jason.

This module defines references and admission rules only. It does not write to a
filesystem, object store, SharePoint, or any provider directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Mapping
from uuid import uuid4


class ArtifactKind(StrEnum):
    EVIDENCE = "evidence"
    REPORT = "report"
    EXPORT = "export"
    ATTACHMENT = "attachment"
    TRANSCRIPT = "transcript"
    SNAPSHOT = "snapshot"


class Sensitivity(StrEnum):
    INTERNAL = "internal"
    CLIENT_CONFIDENTIAL = "client_confidential"
    SECURITY_SENSITIVE = "security_sensitive"
    REGULATED = "regulated"


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    organization_id: str
    kind: ArtifactKind
    media_type: str
    sensitivity: Sensitivity
    source_capability: str
    source_operation: str
    correlation_id: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        required = {
            "organization_id": self.organization_id,
            "media_type": self.media_type,
            "source_capability": self.source_capability,
            "source_operation": self.source_operation,
            "correlation_id": self.correlation_id,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Missing required artifact fields: {', '.join(sorted(missing))}")


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    artifact_id: str
    organization_id: str
    kind: ArtifactKind
    sensitivity: Sensitivity
    media_type: str
    content_sha256: str
    size_bytes: int
    storage_provider: str
    storage_locator: str
    created_at: str
    source_capability: str
    source_operation: str
    correlation_id: str


class ArtifactAdmissionError(ValueError):
    """Raised when artifact storage would violate a governance boundary."""


def admit_artifact(
    descriptor: ArtifactDescriptor,
    content: bytes,
    *,
    storage_provider: str,
    storage_locator: str,
    active_organization_id: str,
) -> ArtifactReference:
    """Create a governed immutable reference after validating tenant scope.

    The caller is responsible for performing the physical storage operation via
    an orchestrator-approved storage capability. Raw artifact bytes should not
    be passed between agents.
    """

    descriptor.validate()
    if descriptor.organization_id != active_organization_id:
        raise ArtifactAdmissionError("Artifact organization does not match active organization context")
    if not storage_provider.strip() or not storage_locator.strip():
        raise ArtifactAdmissionError("Storage provider and locator are required")
    if not content:
        raise ArtifactAdmissionError("Empty artifacts are not admitted")

    return ArtifactReference(
        artifact_id=str(uuid4()),
        organization_id=descriptor.organization_id,
        kind=descriptor.kind,
        sensitivity=descriptor.sensitivity,
        media_type=descriptor.media_type,
        content_sha256=sha256(content).hexdigest(),
        size_bytes=len(content),
        storage_provider=storage_provider,
        storage_locator=storage_locator,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_capability=descriptor.source_capability,
        source_operation=descriptor.source_operation,
        correlation_id=descriptor.correlation_id,
    )
