from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)

from .production_promotion_approval import ProductionPromotionAuthorization


PERMIT_SCHEMA_VERSION = "1.0"
PRODUCTION_ENVIRONMENT = "production"


class ProductionPromotionPermitError(PermissionError):
    pass


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _require_sha256(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return normalized


def _require_source_sha(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 40 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError("source_sha must contain 40 hexadecimal characters")
    return normalized


def _require_artifact_digest(value: str) -> str:
    normalized = str(value or "").strip().lower()
    prefix = "sha256:"
    body = normalized[len(prefix):] if normalized.startswith(prefix) else ""
    if len(body) != 64 or any(c not in "0123456789abcdef" for c in body):
        raise ValueError("artifact_digest must be sha256:<64 hexadecimal characters>")
    return normalized


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProductionPromotionPermit:
    permit_id: str
    approval_id: str
    promotion_id: str
    plan_sha256: str
    target_environment: str
    component: str
    operation: str
    source_sha: str
    artifact_digest: str
    authority_context_id: str
    issued_at: datetime
    expires_at: datetime
    signer_key_id: str
    signature: str

    def unsigned_material(self) -> dict[str, Any]:
        return {
            "schema_version": PERMIT_SCHEMA_VERSION,
            "permit_id": self.permit_id,
            "approval_id": self.approval_id,
            "promotion_id": self.promotion_id,
            "plan_sha256": self.plan_sha256,
            "target_environment": self.target_environment,
            "component": self.component,
            "operation": self.operation,
            "source_sha": self.source_sha,
            "artifact_digest": self.artifact_digest,
            "authority_context_id": self.authority_context_id,
            "issued_at": self.issued_at.astimezone(timezone.utc).isoformat(),
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
            "signer_key_id": self.signer_key_id,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.unsigned_material(), "signature": self.signature}

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ProductionPromotionPermit":
        if str(raw.get("schema_version") or "") != PERMIT_SCHEMA_VERSION:
            raise ProductionPromotionPermitError("unsupported Production permit schema")
        try:
            issued_at = datetime.fromisoformat(str(raw["issued_at"]))
            expires_at = datetime.fromisoformat(str(raw["expires_at"]))
        except (KeyError, ValueError) as exc:
            raise ProductionPromotionPermitError("invalid Production permit timestamps") from exc
        issued_at = _aware_utc(issued_at, "issued_at")
        expires_at = _aware_utc(expires_at, "expires_at")
        return cls(
            permit_id=str(raw.get("permit_id") or "").strip(),
            approval_id=str(raw.get("approval_id") or "").strip(),
            promotion_id=str(raw.get("promotion_id") or "").strip(),
            plan_sha256=_require_sha256(str(raw.get("plan_sha256") or ""), "plan_sha256"),
            target_environment=str(raw.get("target_environment") or "").strip(),
            component=str(raw.get("component") or "").strip(),
            operation=str(raw.get("operation") or "").strip(),
            source_sha=_require_source_sha(str(raw.get("source_sha") or "")),
            artifact_digest=_require_artifact_digest(str(raw.get("artifact_digest") or "")),
            authority_context_id=str(raw.get("authority_context_id") or "").strip(),
            issued_at=issued_at,
            expires_at=expires_at,
            signer_key_id=str(raw.get("signer_key_id") or "").strip(),
            signature=str(raw.get("signature") or "").strip(),
        )


@dataclass(frozen=True, slots=True)
class ProductionPromotionPermitIssuer:
    private_key_pem: bytes
    signer_key_id: str
    maximum_ttl: timedelta = timedelta(minutes=15)

    def issue(
        self,
        *,
        authorization: ProductionPromotionAuthorization,
        component: str,
        operation: str,
        source_sha: str,
        artifact_digest: str,
        now: datetime | None = None,
        ttl: timedelta = timedelta(minutes=10),
    ) -> ProductionPromotionPermit:
        issued_at = _aware_utc(now or datetime.now(timezone.utc), "now")
        if ttl <= timedelta(0) or ttl > self.maximum_ttl:
            raise ValueError("Production permit TTL is outside the permitted window")
        expires_at = min(issued_at + ttl, _aware_utc(authorization.expires_at, "authorization.expires_at"))
        if expires_at <= issued_at:
            raise ProductionPromotionPermitError("Owner authorization is expired")

        component_value = component.strip()
        operation_value = operation.strip()
        if not component_value or not operation_value:
            raise ValueError("component and operation must be non-empty")
        key_id = self.signer_key_id.strip()
        if not key_id:
            raise ValueError("signer_key_id must be non-empty")

        material = {
            "schema_version": PERMIT_SCHEMA_VERSION,
            "permit_id": f"prod-permit-{uuid4().hex}",
            "approval_id": authorization.approval_id,
            "promotion_id": authorization.promotion_id,
            "plan_sha256": _require_sha256(authorization.plan_sha256, "plan_sha256"),
            "target_environment": PRODUCTION_ENVIRONMENT,
            "component": component_value,
            "operation": operation_value,
            "source_sha": _require_source_sha(source_sha),
            "artifact_digest": _require_artifact_digest(artifact_digest),
            "authority_context_id": authorization.authority_context_id,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "signer_key_id": key_id,
        }
        private_key = load_pem_private_key(self.private_key_pem, password=None)
        signature = private_key.sign(canonical_json_bytes(material))
        return ProductionPromotionPermit.from_mapping(
            {
                **material,
                "signature": base64.b64encode(signature).decode("ascii"),
            }
        )


@dataclass(frozen=True, slots=True)
class ProductionPromotionPermitVerifier:
    public_keys: Mapping[str, bytes]

    def verify(
        self,
        permit: ProductionPromotionPermit,
        *,
        component: str,
        operation: str,
        source_sha: str,
        artifact_digest: str,
        plan_sha256: str,
        now: datetime | None = None,
    ) -> None:
        current = _aware_utc(now or datetime.now(timezone.utc), "now")
        if permit.target_environment != PRODUCTION_ENVIRONMENT:
            raise ProductionPromotionPermitError("permit target is not Production")
        if permit.component != component.strip():
            raise ProductionPromotionPermitError("permit component mismatch")
        if permit.operation != operation.strip():
            raise ProductionPromotionPermitError("permit operation mismatch")
        if permit.source_sha != _require_source_sha(source_sha):
            raise ProductionPromotionPermitError("permit source SHA mismatch")
        if permit.artifact_digest != _require_artifact_digest(artifact_digest):
            raise ProductionPromotionPermitError("permit artifact digest mismatch")
        if permit.plan_sha256 != _require_sha256(plan_sha256, "plan_sha256"):
            raise ProductionPromotionPermitError("permit plan fingerprint mismatch")
        if not permit.permit_id or not permit.approval_id or not permit.promotion_id:
            raise ProductionPromotionPermitError("permit identifiers are missing")
        if not permit.authority_context_id:
            raise ProductionPromotionPermitError("permit authority context is missing")
        if permit.issued_at > current:
            raise ProductionPromotionPermitError("permit issue time is in the future")
        if permit.expires_at <= current:
            raise ProductionPromotionPermitError("permit has expired")
        if permit.expires_at <= permit.issued_at:
            raise ProductionPromotionPermitError("permit lifetime is invalid")

        public_key_pem = self.public_keys.get(permit.signer_key_id)
        if public_key_pem is None:
            raise ProductionPromotionPermitError("permit signer is not trusted")
        try:
            signature = base64.b64decode(permit.signature, validate=True)
        except Exception as exc:
            raise ProductionPromotionPermitError("permit signature encoding is invalid") from exc
        public_key = load_pem_public_key(public_key_pem)
        try:
            public_key.verify(signature, canonical_json_bytes(permit.unsigned_material()))
        except InvalidSignature as exc:
            raise ProductionPromotionPermitError("permit signature is invalid") from exc


@dataclass(frozen=True, slots=True)
class ProductionPromotionPermitClaim:
    permit_id: str
    approval_id: str
    promotion_id: str
    plan_sha256: str
    component: str
    operation: str
    source_sha: str
    artifact_digest: str
    claimed_at: datetime


@dataclass(frozen=True, slots=True)
class SQLiteProductionPromotionPermitClaims:
    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS production_promotion_permit_claims (
                    permit_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    promotion_id TEXT NOT NULL,
                    plan_sha256 TEXT NOT NULL,
                    component TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    source_sha TEXT NOT NULL,
                    artifact_digest TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_prod_permit_claims_promotion
                ON production_promotion_permit_claims(promotion_id, claimed_at);
                """
            )

    def claim(self, permit: ProductionPromotionPermit, *, now: datetime | None = None) -> ProductionPromotionPermitClaim:
        claimed_at = _aware_utc(now or datetime.now(timezone.utc), "now")
        claim = ProductionPromotionPermitClaim(
            permit_id=permit.permit_id,
            approval_id=permit.approval_id,
            promotion_id=permit.promotion_id,
            plan_sha256=permit.plan_sha256,
            component=permit.component,
            operation=permit.operation,
            source_sha=permit.source_sha,
            artifact_digest=permit.artifact_digest,
            claimed_at=claimed_at,
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT permit_id FROM production_promotion_permit_claims WHERE permit_id=?",
                    (permit.permit_id,),
                ).fetchone()
                if existing is not None:
                    raise ProductionPromotionPermitError("Production permit has already been consumed")
                connection.execute(
                    """
                    INSERT INTO production_promotion_permit_claims(
                        permit_id, approval_id, promotion_id, plan_sha256, component,
                        operation, source_sha, artifact_digest, claimed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim.permit_id,
                        claim.approval_id,
                        claim.promotion_id,
                        claim.plan_sha256,
                        claim.component,
                        claim.operation,
                        claim.source_sha,
                        claim.artifact_digest,
                        claim.claimed_at.isoformat(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ProductionPromotionPermitError("Production permit has already been consumed") from exc
            except Exception:
                connection.rollback()
                raise
        return claim

    def evidence(self, permit_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM production_promotion_permit_claims WHERE permit_id=?",
                (permit_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection


def load_permit(path: str | Path) -> ProductionPromotionPermit:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProductionPromotionPermitError("Production permit must be a JSON object")
    return ProductionPromotionPermit.from_mapping(raw)


def permit_payload_sha256(permit: ProductionPromotionPermit) -> str:
    return hashlib.sha256(canonical_json_bytes(permit.as_dict())).hexdigest()


DEFAULT_TRUSTED_KEY_REGISTRY = Path(
    "/var/lib/jason/authority/production-promotion-trusted-keys.json"
)
DEFAULT_PERMIT_CLAIMS_DB = Path(
    "/var/lib/jason/authority/production-promotion-permit-claims.sqlite3"
)


def load_trusted_public_keys(
    path: str | Path = DEFAULT_TRUSTED_KEY_REGISTRY,
) -> dict[str, bytes]:
    registry_path = Path(path)
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != "1.0":
        raise ProductionPromotionPermitError("invalid Production trusted-key registry")
    keys = raw.get("keys")
    if not isinstance(keys, list):
        raise ProductionPromotionPermitError("Production trusted-key registry keys are invalid")
    public_keys: dict[str, bytes] = {}
    for item in keys:
        if not isinstance(item, dict) or item.get("status") != "active":
            continue
        key_id = str(item.get("key_id") or "").strip()
        key_path_text = str(item.get("public_key_path") or "").strip()
        expected_sha = str(item.get("public_key_sha256") or "").strip().lower()
        if not key_id or not key_path_text:
            raise ProductionPromotionPermitError("active Production key record is incomplete")
        key_path = Path(key_path_text)
        if not key_path.is_absolute():
            raise ProductionPromotionPermitError("Production public key path must be absolute")
        pem = key_path.read_bytes()
        actual_sha = hashlib.sha256(pem).hexdigest()
        if expected_sha and actual_sha != _require_sha256(expected_sha, "public_key_sha256"):
            raise ProductionPromotionPermitError("Production public key fingerprint mismatch")
        if key_id in public_keys:
            raise ProductionPromotionPermitError("duplicate Production signer key ID")
        public_keys[key_id] = pem
    if not public_keys:
        raise ProductionPromotionPermitError("no active Production promotion signing keys")
    return public_keys


def verify_and_claim_production_permit(
    *,
    permit_path: str | Path,
    component: str,
    operation: str,
    source_sha: str,
    artifact_digest: str,
    plan_sha256: str,
    now: datetime | None = None,
    trusted_key_registry: str | Path = DEFAULT_TRUSTED_KEY_REGISTRY,
    claims_database: str | Path = DEFAULT_PERMIT_CLAIMS_DB,
    claim: bool = True,
) -> ProductionPromotionPermit:
    permit = load_permit(permit_path)
    verifier = ProductionPromotionPermitVerifier(
        public_keys=load_trusted_public_keys(trusted_key_registry)
    )
    verifier.verify(
        permit,
        component=component,
        operation=operation,
        source_sha=source_sha,
        artifact_digest=artifact_digest,
        plan_sha256=plan_sha256,
        now=now,
    )
    if claim:
        claims = SQLiteProductionPromotionPermitClaims(str(claims_database))
        claims.initialize()
        claims.claim(permit, now=now)
    return permit
