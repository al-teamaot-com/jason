from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class CandidateHostAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateHostIdentity:
    schema_version: str
    environment: str
    instance_id: str
    bootstrap_authorized: bool


def validate_candidate_host_identity(
    identity: CandidateHostIdentity,
) -> CandidateHostIdentity:
    if identity.schema_version != "1.0":
        raise CandidateHostAuthorizationError(
            "unsupported candidate-host identity schema"
        )
    if identity.environment != "candidate":
        raise CandidateHostAuthorizationError(
            "host identity is not candidate"
        )
    if not identity.instance_id.strip():
        raise CandidateHostAuthorizationError(
            "candidate instance_id is missing"
        )
    if not identity.bootstrap_authorized:
        raise CandidateHostAuthorizationError(
            "candidate bootstrap is not authorized"
        )
    return identity


def load_candidate_host_identity(
    path: str | Path,
) -> CandidateHostIdentity:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = CandidateHostIdentity(
        schema_version=str(payload.get("schema_version") or ""),
        environment=str(payload.get("environment") or ""),
        instance_id=str(payload.get("instance_id") or ""),
        bootstrap_authorized=bool(payload.get("bootstrap_authorized")),
    )
    return validate_candidate_host_identity(identity)


def authorize_mutation_target(
    *,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity | None,
    operation: str,
) -> Path:
    root = Path(target_root)
    if not root.is_absolute():
        raise CandidateHostAuthorizationError(
            f"{operation}: target_root must be absolute"
        )
    if root != Path("/"):
        return root
    if candidate_identity is None:
        raise CandidateHostAuthorizationError(
            f"{operation}: live filesystem root mutation requires explicit candidate-host identity"
        )
    validate_candidate_host_identity(candidate_identity)
    return root
