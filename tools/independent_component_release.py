#!/usr/bin/env python3
"""Reusable, source-only independent-component release transaction.

This module is NOT an installer and grants no production authority.
A separate root-owned host installation must supply all callbacks from
independently reviewed immutable code. Importing this file changes nothing.
It does not invoke Docker, touch PMV3/PMv4, or change the production freeze.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Callable, ContextManager, Mapping

import yaml

from implementation.kernel.signed_owner_release import (
    canonical, read_pinned_root_owner_public_key, verify_exact_owner_release,
)

SHA = re.compile(r"^[a-f0-9]{40}$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
IMAGE = re.compile(r"^sha256:[a-f0-9]{64}$")
ZERO = "0" * 40
PRODUCTION_ROOT = Path("/var/lib/jason/independent-component-release")
TRUSTED_SOURCE = Path("/opt/jason/independent-component-release/trusted/tools/independent_component_release.py")
OWNER_TRUST = Path("/etc/jason-owner-release/verified-owner-public-key.json")
PMV3_FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
PROTECTED = (
    "jason-mcp-pilot", "jason-pmv4-shadow-gateway",
    "jason-runtime", "jason-teams-gateway", "openbao",
)
RELEASE_FIELDS = {
    "schema_version", "release_mode", "repository", "component_id",
    "compose_project", "compose_service", "candidate_sha", "rollback_sha",
    "image_digest", "compose_sha256", "config_sha256", "boundary_sha256",
    "scope_sha256", "freeze_sha256", "provider_scope", "protected_services",
    "rollback_mode",
}
SCOPE_FIELDS = RELEASE_FIELDS - {"release_mode", "repository", "scope_sha256", "freeze_sha256"}
PROVIDER_FIELDS = {"provider", "profile", "tenant_id", "scope_id", "application_id", "client_id"}
DENIED_PROJECTS = {
    "jason-runtime", "jason-mcp", "jason-pmv4-shadow", "openclaw",
}


class ComponentReleaseDenied(PermissionError):
    """An exact-scoped release is not admissible."""


def digest(blob: bytes) -> str:
    return sha256(blob).hexdigest()


def release_id(sha: str) -> str:
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise ComponentReleaseDenied("COMPONENT_SOURCE_SHA_INVALID")
    return "release-" + sha[:16]


def _sha(value: Any) -> bool:
    return type(value) is str and SHA.fullmatch(value) is not None


def _digest(value: Any) -> bool:
    return type(value) is str and DIGEST.fullmatch(value) is not None


def _slug(value: Any) -> bool:
    return type(value) is str and SLUG.fullmatch(value) is not None


def _exact_fields(value: Any, fields: set[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ComponentReleaseDenied(code)


def _provider(value: Any) -> None:
    _exact_fields(value, PROVIDER_FIELDS, "COMPONENT_PROVIDER_SCOPE_SCHEMA")
    if value["provider"] == "none":
        if any(value[k] for k in ("profile", "tenant_id", "scope_id", "application_id", "client_id")):
            raise ComponentReleaseDenied("COMPONENT_PROVIDER_NONE_SCOPE")
    elif not all(
        isinstance(value[k], str) and 0 < len(value[k]) <= 256
        for k in PROVIDER_FIELDS
    ):
        raise ComponentReleaseDenied("COMPONENT_PROVIDER_SCOPE_INVALID")


def validate_manifest(m: Mapping[str, Any]) -> None:
    _exact_fields(m, RELEASE_FIELDS, "COMPONENT_MANIFEST_SCHEMA")
    if (
        m["schema_version"] != "1.0"
        or m["release_mode"] != "owner-signed-independent-compose"
        or m["repository"] != "al-teamaot-com/jason"
        or not _slug(m["component_id"])
        or not _slug(m["compose_project"])
        or not m["compose_project"].startswith("jason-")
        or m["compose_project"] in DENIED_PROJECTS
        or not _slug(m["compose_service"])
        or not _sha(m["candidate_sha"])
        or not _sha(m["rollback_sha"])
        or m["candidate_sha"] == m["rollback_sha"]
        or not isinstance(m["image_digest"], str)
        or IMAGE.fullmatch(m["image_digest"]) is None
        or not all(_digest(m[key]) for key in (
            "compose_sha256", "config_sha256", "boundary_sha256",
            "scope_sha256", "freeze_sha256",
        ))
        or m["protected_services"] != list(PROTECTED)
        or m["rollback_mode"] != (
            "remove-component-only" if m["rollback_sha"] == ZERO
            else "restore-prior-component-only"
        )
    ):
        raise ComponentReleaseDenied("COMPONENT_MANIFEST_FIELDS")
    _provider(m["provider_scope"])
    if m["provider_scope"]["provider"] == "none" and m["boundary_sha256"] != "0" * 64:
        raise ComponentReleaseDenied("COMPONENT_PROVIDERLESS_BOUNDARY")
    if m["provider_scope"]["provider"] != "none" and m["boundary_sha256"] == "0" * 64:
        raise ComponentReleaseDenied("COMPONENT_BOUNDARY_REQUIRED")


def validate_scope(m: Mapping[str, Any], scope: Mapping[str, Any]) -> None:
    _exact_fields(scope, SCOPE_FIELDS, "COMPONENT_SCOPE_SCHEMA")
    expected = {key: m[key] for key in SCOPE_FIELDS}
    if scope != expected or digest(canonical(scope)) != m["scope_sha256"]:
        raise ComponentReleaseDenied("COMPONENT_SCOPE_MISMATCH")


def validate_compose(content: bytes, m: Mapping[str, Any]) -> None:
    """Reject escalation and all cross-component Compose dependencies.

    The root-installed host adapter must additionally resolve and pin every
    interpolation variable and host mount before executing Docker Compose.
    """
    try:
        y = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_YAML_INVALID") from exc
    if not isinstance(y, dict) or y.get("name") != m["compose_project"]:
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_PROJECT_MISMATCH")
    services = y.get("services")
    if not isinstance(services, dict) or set(services) != {m["compose_service"]}:
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_MULTISERVICE_DENIED")
    c = services[m["compose_service"]]
    if not isinstance(c, dict):
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_SERVICE_INVALID")
    if any(name in c for name in (
        "build", "privileged", "pid", "ipc", "network_mode", "extra_hosts",
        "devices", "depends_on", "links", "ports", "volumes_from",
        "container_name", "userns_mode", "cgroup_parent",
    )):
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_ESCALATION_DENIED")
    if (
        c.get("read_only") is not True
        or str(c.get("user")) != "1000:1000"
        or c.get("cap_drop") != ["ALL"]
        or "no-new-privileges:true" not in c.get("security_opt", [])
        or not isinstance(c.get("image"), str)
        or c.get("image") == ""
    ):
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_ISOLATION_DENIED")
    raw = content.decode("utf-8", errors="strict")
    if any(bad in raw for bad in (
        "/var/run/docker.sock", "/run/docker.sock", "/var/lib/jason/authority",
        "/var/lib/jason/openclaw", "/opt/jason/releases",
    )):
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_PROTECTED_MOUNT_DENIED")
    if not isinstance(c.get("volumes"), list):
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_VOLUME_CONTRACT_MISSING")
    for mount in c["volumes"]:
        if not isinstance(mount, str) or mount.count(":") < 2:
            raise ComponentReleaseDenied("COMPONENT_COMPOSE_VOLUME_INVALID")
        if mount.rsplit(":", 1)[-1] not in ("ro", "rw"):
            raise ComponentReleaseDenied("COMPONENT_COMPOSE_VOLUME_MODE_UNPINNED")
    if any(k not in {"name", "services", "networks", "volumes"} for k in y):
        raise ComponentReleaseDenied("COMPONENT_COMPOSE_TOPLEVEL_UNREVIEWED")


def validate_boundary_snapshot(path: Path, m: Mapping[str, Any]) -> None:
    """One validated tenant/client/site only; never read live runtime authority.

    The installed host must stage this snapshot as a root-owned immutable file.
    It cannot be a live SQLite database, a delegated user token, or a directory-
    read boundary. This check is in addition to the signed exact file digest.
    """
    from urllib.parse import quote
    scope = m["provider_scope"]
    if scope["provider"] == "none":
        return
    uri = "file:" + quote(str(path), safe="/") + "?mode=ro&immutable=1"
    try:
        with sqlite3.connect(uri, uri=True) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ComponentReleaseDenied("COMPONENT_BOUNDARY_SQLITE_INTEGRITY")
            rows = db.execute(
                "SELECT client_id,provider,external_tenant_id,profile,"
                "application_id,status,external_scope_ids FROM client_boundaries"
            ).fetchall()
            tx_count = db.execute(
                "SELECT count(*) FROM onboarding_transactions"
            ).fetchone()[0]
    except sqlite3.DatabaseError as exc:
        raise ComponentReleaseDenied("COMPONENT_BOUNDARY_SQLITE_INVALID") from exc
    if len(rows) != 1 or tx_count != 0:
        raise ComponentReleaseDenied("COMPONENT_BOUNDARY_NOT_SINGLE_VALIDATED")
    row = rows[0]
    try:
        scopes = json.loads(row[6])
    except (ValueError, TypeError) as exc:
        raise ComponentReleaseDenied("COMPONENT_BOUNDARY_SITE_SCOPE_INVALID") from exc
    if (
        row[:6] != (
            scope["client_id"], scope["provider"], scope["tenant_id"],
            scope["profile"], scope["application_id"], "validated",
        )
        or scopes != [scope["scope_id"]]
    ):
        raise ComponentReleaseDenied("COMPONENT_BOUNDARY_SITE_SCOPE_INVALID")


def trusted_file(path: Path, *, production: bool = True, max_bytes: int = 1024 * 1024, allow_owner_write: bool = False, allowed_uid: int = 0) -> bytes:
    try:
        meta = path.lstat()
        if (
            not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or meta.st_size < 1 or meta.st_size > max_bytes
            or path.is_symlink()
            or (production and (
                meta.st_uid != allowed_uid or stat.S_IMODE(meta.st_mode) & 0o022
                or (not allow_owner_write and stat.S_IMODE(meta.st_mode) & 0o200)
            ))
        ):
            raise ComponentReleaseDenied("COMPONENT_BUNDLE_FILE_UNTRUSTED")
        return path.read_bytes()
    except OSError as exc:
        raise ComponentReleaseDenied("COMPONENT_BUNDLE_FILE_UNAVAILABLE") from exc


def trusted_dir(path: Path, *, production: bool) -> None:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise ComponentReleaseDenied("COMPONENT_CONTROL_ROOT_UNAVAILABLE") from exc
    if (
        path.is_symlink() or not stat.S_ISDIR(meta.st_mode)
        or (production and (meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022))
    ):
        raise ComponentReleaseDenied("COMPONENT_CONTROL_ROOT_UNTRUSTED")


def _load_json(blob: bytes) -> dict[str, Any]:
    try:
        value = json.loads(blob)
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        raise ComponentReleaseDenied("COMPONENT_RECORD_JSON_INVALID") from exc


def _atomic_json(path: Path, record: Mapping[str, Any]) -> None:
    """Never follow a caller-created final path or leave a partial journal."""
    if path.exists() or path.is_symlink():
        raise ComponentReleaseDenied("COMPONENT_RECEIPT_REPLAY_OR_CONFLICT")
    b = canonical(record) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(b)
        f.flush()
        os.fsync(f.fileno())
    d = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(d)
    finally:
        os.close(d)


def _replace_json(path: Path, record: Mapping[str, Any]) -> None:
    temp = path.with_name("." + path.name + ".next")
    _atomic_json(temp, record)
    os.replace(temp, path)
    d = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(d)
    finally:
        os.close(d)


@dataclass(frozen=True)
class VerifiedRelease:
    component_id: str
    candidate_sha: str
    rollback_sha: str
    approval_id: str
    manifest_sha256: str
    scope_sha256: str


class ComponentReleaseController:
    """Trusted host orchestration; all production callbacks are installed separately."""

    def __init__(
        self, *, root: Path,
        host_transaction: Callable[[], ContextManager[None]],
        freeze_transaction: Callable[[str], ContextManager[None]],
        verify_protected: Callable[[], Mapping[str, Mapping[str, Any]]],
        verify_source_and_ci: Callable[[str], bool],
        verify_image: Callable[[str, str], bool],
        observe_component: Callable[[str], str | None],
        activate_component: Callable[[Path, Mapping[str, Any]], None],
        restore_component: Callable[[Path | None, Mapping[str, Any]], None],
        verify_component: Callable[[Path | None, Mapping[str, Any]], bool],
        production: bool = True,
        trusted_public_key: Any = None,
    ) -> None:
        if production and (
            os.geteuid() != 0
            or Path(root) != PRODUCTION_ROOT
            or Path(__file__).resolve() != TRUSTED_SOURCE
            or trusted_public_key is not None
        ):
            raise ComponentReleaseDenied("COMPONENT_ROOT_INSTALLED_TRUST_REQUIRED")
        for func in (
            host_transaction, freeze_transaction, verify_protected,
            verify_source_and_ci, verify_image, observe_component,
            activate_component, restore_component, verify_component,
        ):
            if not callable(func):
                raise ComponentReleaseDenied("COMPONENT_TRUSTED_HOST_CALLBACK_MISSING")
        self.root = Path(root)
        self.production = production
        self.host_transaction = host_transaction
        self.freeze_transaction = freeze_transaction
        self.verify_protected = verify_protected
        self.verify_source_and_ci = verify_source_and_ci
        self.verify_image = verify_image
        self.observe_component = observe_component
        self.activate_component = activate_component
        self.restore_component = restore_component
        self.verify_component = verify_component
        self._test_key = trusted_public_key

    def _paths(self) -> tuple[Path, Path, Path, Path]:
        trusted_dir(self.root, production=self.production)
        releases = self.root / "releases"
        receipts = self.root / "receipts"
        control = self.root / "control"
        active = self.root / "active"
        for path in (releases, receipts, control, active):
            trusted_dir(path, production=self.production)
        return releases, receipts, control, active

    def _bundle(self, m: Mapping[str, Any]) -> Path:
        releases, _, _, _ = self._paths()
        bundle = releases / m["candidate_sha"]
        trusted_dir(bundle, production=self.production)
        if _load_json(trusted_file(bundle / "manifest.json", production=self.production)) != m:
            raise ComponentReleaseDenied("COMPONENT_IMMUTABLE_MANIFEST_DRIFT")
        scope = _load_json(trusted_file(bundle / "scope.json", production=self.production))
        validate_scope(m, scope)
        for filename, expected, max_bytes in (
            ("compose.yaml", m["compose_sha256"], 65536),
            ("config.json", m["config_sha256"], 131072),
        ):
            if digest(trusted_file(bundle / filename, production=self.production, max_bytes=max_bytes)) != expected:
                raise ComponentReleaseDenied("COMPONENT_IMMUTABLE_BUNDLE_DRIFT")
        compose = trusted_file(bundle / "compose.yaml", production=self.production, max_bytes=65536)
        validate_compose(compose, m)
        if m["provider_scope"]["provider"] != "none":
            b = trusted_file(bundle / "boundary.sqlite3", production=self.production)
            if digest(b) != m["boundary_sha256"]:
                raise ComponentReleaseDenied("COMPONENT_BOUNDARY_DIGEST_MISMATCH")
            validate_boundary_snapshot(bundle / "boundary.sqlite3", m)
        return bundle

    def _freeze_bytes(self, m: Mapping[str, Any]) -> bytes:
        raw = trusted_file(PMV3_FREEZE if self.production else self.root / "control" / "production-deployment-freeze", production=self.production, max_bytes=4096, allow_owner_write=True, allowed_uid=(1000 if self.production else 0))
        record = _load_json(raw)
        if record.get("status") != "active" or digest(raw) != m["freeze_sha256"]:
            raise ComponentReleaseDenied("COMPONENT_FROZEN_STATE_CHANGED")
        return raw

    def _active(self, component_id: str) -> str | None:
        *_, active = self._paths()
        p = active / (component_id + ".json")
        if not p.exists() and not p.is_symlink():
            return None
        record = _load_json(trusted_file(p, production=self.production, allow_owner_write=True))
        if set(record) != {"component_id", "candidate_sha", "manifest_sha256"}:
            raise ComponentReleaseDenied("COMPONENT_ACTIVE_RECORD_INVALID")
        if record["component_id"] != component_id or not _sha(record["candidate_sha"]) or not _digest(record["manifest_sha256"]):
            raise ComponentReleaseDenied("COMPONENT_ACTIVE_RECORD_INVALID")
        return record["candidate_sha"]

    def _verify_protected_snapshot(self) -> Mapping[str, Mapping[str, Any]]:
        observed = self.verify_protected()
        if not isinstance(observed, Mapping) or set(observed) != set(PROTECTED):
            raise ComponentReleaseDenied("COMPONENT_PROTECTED_HEALTH_UNVERIFIED")
        for entry in observed.values():
            if not isinstance(entry, Mapping) or entry.get("running") is not True or (
                entry.get("health") not in ("healthy", "none", None)
            ) or any(not isinstance(entry.get(k), str) or not entry.get(k) for k in ("id", "image", "started_at")):
                raise ComponentReleaseDenied("COMPONENT_PROTECTED_HEALTH_UNVERIFIED")
        return observed

    @staticmethod
    def _same_protected(a: Mapping[str, Mapping[str, Any]], b: Mapping[str, Mapping[str, Any]]) -> bool:
        return all(
            all(a[n][k] == b[n][k] for k in ("id", "image", "started_at"))
            for n in PROTECTED
        )

    def _check_pending(self, receipts: Path) -> frozenset[str]:
        consumed: set[str] = set()
        for file in receipts.iterdir():
            if file.is_symlink() or not file.is_file() or file.suffix != ".json":
                raise ComponentReleaseDenied("COMPONENT_RECEIPT_STORE_UNTRUSTED")
            value = _load_json(trusted_file(file, production=self.production, allow_owner_write=True))
            if value.get("state") not in ("accepted", "rolled_back"):
                raise ComponentReleaseDenied("COMPONENT_UNRESOLVED_TRANSACTION")
            if file.name != "owner-" + str(value.get("approval_id")) + ".json":
                raise ComponentReleaseDenied("COMPONENT_RECEIPT_ID_MISMATCH")
            consumed.add(str(value["approval_id"]))
        return frozenset(consumed)

    def preflight(
        self, manifest: Mapping[str, Any], signed_approval: Mapping[str, Any],
        *, at: datetime | None = None,
    ) -> tuple[VerifiedRelease, Path, Mapping[str, Mapping[str, Any]]]:
        """Only call while holding the shared host and component locks."""
        validate_manifest(manifest)
        releases, receipts, _, _ = self._paths()
        component_id = manifest["component_id"]
        prev = self._active(component_id)
        rollback = manifest["rollback_sha"]
        if prev != (None if rollback == ZERO else rollback):
            raise ComponentReleaseDenied("COMPONENT_ROLLBACK_NOT_CURRENT")
        observed = self.observe_component(manifest["compose_project"])
        if observed != prev:
            raise ComponentReleaseDenied("COMPONENT_INSTALLED_BASELINE_MISMATCH")
        bundle = self._bundle(manifest)
        if rollback != ZERO:
            previous = releases / rollback
            trusted_dir(previous, production=self.production)
            prior = _load_json(trusted_file(previous / "manifest.json", production=self.production))
            validate_manifest(prior)
            if prior["component_id"] != component_id or prior["candidate_sha"] != rollback:
                raise ComponentReleaseDenied("COMPONENT_PREVIOUS_BUNDLE_INVALID")
            self._bundle(prior)
        if self.verify_source_and_ci(manifest["candidate_sha"]) is not True:
            raise ComponentReleaseDenied("COMPONENT_PROTECTED_SOURCE_OR_CI_UNVERIFIED")
        if self.verify_image(manifest["image_digest"], manifest["candidate_sha"]) is not True:
            raise ComponentReleaseDenied("COMPONENT_IMAGE_PROVENANCE_UNVERIFIED")
        baseline = self._verify_protected_snapshot()
        self._freeze_bytes(manifest)
        consumed = self._check_pending(receipts)
        if self.production:
            key = read_pinned_root_owner_public_key(OWNER_TRUST)
        else:
            key = self._test_key
        release = verify_exact_owner_release(
            signed_approval,
            public_key=key,
            expected_release_id=release_id(manifest["candidate_sha"]),
            expected_candidate_sha=manifest["candidate_sha"],
            expected_rollback_sha=rollback,
            expected_scope_sha256=manifest["scope_sha256"],
            expected_manifest_sha256=digest(canonical(manifest)),
            expected_freeze_sha256=manifest["freeze_sha256"],
            at=at or datetime.now(timezone.utc),
            consumed_ids=consumed,
        )
        return (
            VerifiedRelease(
                component_id, manifest["candidate_sha"], rollback,
                release["approval_id"], digest(canonical(manifest)), manifest["scope_sha256"],
            ),
            bundle, baseline,
        )

    def promote(self, manifest: Mapping[str, Any], signed_approval: Mapping[str, Any]) -> dict[str, Any]:
        """One bounded component-only transaction; never callable from untrusted source."""
        with self.host_transaction():
            *_, control, active_dir = self._paths()
            lock = control / "component-release.lock"
            trusted_file(lock, production=self.production, max_bytes=4096, allow_owner_write=True)
            with lock.open("rb") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ComponentReleaseDenied("COMPONENT_TRANSACTION_BUSY") from exc
                verified, bundle, baseline = self.preflight(manifest, signed_approval)
                _, receipts, _, _ = self._paths()
                receipt = receipts / ("owner-" + verified.approval_id + ".json")
                previous = None if verified.rollback_sha == ZERO else self.root / "releases" / verified.rollback_sha
                journal: dict[str, Any] = {
                    "schema_version": "1.0", "state": "started",
                    "component_id": verified.component_id, "release_id": release_id(verified.candidate_sha),
                    "approval_id": verified.approval_id, "candidate_sha": verified.candidate_sha,
                    "rollback_sha": verified.rollback_sha,
                    "manifest_sha256": verified.manifest_sha256,
                    "scope_sha256": verified.scope_sha256,
                    "freeze_sha256": manifest["freeze_sha256"],
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "protected_before": dict(baseline),
                    "signed_owner_proof": dict(signed_approval),
                }
                _atomic_json(receipt, journal)
                try:
                    with self.freeze_transaction(manifest["freeze_sha256"]):
                        try:
                            self.activate_component(bundle, manifest)
                            if self.observe_component(manifest["compose_project"]) != verified.candidate_sha:
                                raise ComponentReleaseDenied("COMPONENT_ACTIVATION_READBACK_FAILED")
                            if self.verify_component(bundle, manifest) is not True:
                                raise ComponentReleaseDenied("COMPONENT_ACCEPTANCE_FAILED")
                            after = self._verify_protected_snapshot()
                            if not self._same_protected(baseline, after):
                                raise ComponentReleaseDenied("COMPONENT_PROTECTED_RUNTIME_CHANGED")
                        except BaseException:
                            try:
                                self.restore_component(previous, manifest)
                                if self.observe_component(manifest["compose_project"]) != (
                                    None if previous is None else verified.rollback_sha
                                ):
                                    raise ComponentReleaseDenied("COMPONENT_ROLLBACK_READBACK_FAILED")
                                if self.verify_component(previous, manifest) is not True:
                                    raise ComponentReleaseDenied("COMPONENT_ROLLBACK_ACCEPTANCE_FAILED")
                                if not self._same_protected(baseline, self._verify_protected_snapshot()):
                                    raise ComponentReleaseDenied("COMPONENT_ROLLBACK_PROTECTED_DRIFT")
                                journal["state"] = "rolled_back"
                                journal["finished_at"] = datetime.now(timezone.utc).isoformat()
                                _replace_json(receipt, journal)
                            except BaseException:
                                # Unresolved STARTED receipt blocks all future releases.
                                pass
                            raise
                    self._freeze_bytes(manifest)
                    # Root-controlled active pointer changes only after verified acceptance.
                    current = active_dir / (verified.component_id + ".json")
                    record = {
                        "component_id": verified.component_id,
                        "candidate_sha": verified.candidate_sha,
                        "manifest_sha256": verified.manifest_sha256,
                    }
                    if current.exists() or current.is_symlink():
                        _replace_json(current, record)
                    else:
                        _atomic_json(current, record)
                    journal["state"] = "accepted"
                    journal["finished_at"] = datetime.now(timezone.utc).isoformat()
                    _replace_json(receipt, journal)
                except BaseException:
                    # Never claim successful activation from a partial transaction.
                    raise
                return {
                    "status": "component_accepted",
                    "component_id": verified.component_id,
                    "candidate_sha": verified.candidate_sha,
                    "rollback_sha": verified.rollback_sha,
                    "approval_id": verified.approval_id,
                    "protected_services_changed": False,
                }

    def recover_interrupted_rollback(self) -> dict[str, Any]:
        """Root-only recovery of ONE previously signed, started transaction.

        Recovery never accepts a new candidate and cannot create a fresh release.
        It revalidates the original signature at its recorded start time, checks
        the pinned staged manifest and the unchanged freeze, then stops/restores
        ONLY the component under the same host lock. Ambiguity fails closed.
        """
        with self.host_transaction():
            releases, receipts, control, active = self._paths()
            lock = control / "component-release.lock"
            trusted_file(lock, production=self.production, max_bytes=4096, allow_owner_write=True)
            with lock.open("rb") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ComponentReleaseDenied("COMPONENT_TRANSACTION_BUSY") from exc
                pending: list[tuple[Path, dict[str, Any]]] = []
                for path in receipts.iterdir():
                    value = _load_json(trusted_file(
                        path, production=self.production, allow_owner_write=True,
                    ))
                    if path.name != "owner-" + str(value.get("approval_id")) + ".json":
                        raise ComponentReleaseDenied("COMPONENT_RECOVERY_RECEIPT_INVALID")
                    if value.get("state") == "started":
                        pending.append((path, value))
                    elif value.get("state") not in ("rolled_back", "accepted"):
                        raise ComponentReleaseDenied("COMPONENT_RECOVERY_UNKNOWN_STATE")
                if not pending:
                    return {"status": "nothing_pending", "production_mutation": False}
                if len(pending) != 1:
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_MULTIPLE_PENDING")
                path, journal = pending[0]
                candidate = journal.get("candidate_sha")
                rollback = journal.get("rollback_sha")
                component = journal.get("component_id")
                if not _sha(candidate) or not _sha(rollback) or not _slug(component):
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_IDENTITY_INVALID")
                bundle = releases / candidate
                manifest = _load_json(trusted_file(
                    bundle / "manifest.json", production=self.production,
                ))
                validate_manifest(manifest)
                if (
                    manifest["candidate_sha"] != candidate
                    or manifest["rollback_sha"] != rollback
                    or manifest["component_id"] != component
                    or journal.get("release_id") != release_id(candidate)
                    or journal.get("manifest_sha256") != digest(canonical(manifest))
                    or journal.get("scope_sha256") != manifest["scope_sha256"]
                    or journal.get("freeze_sha256") != manifest["freeze_sha256"]
                ):
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_SCOPE_INVALID")
                self._bundle(manifest)
                if self.production:
                    key = read_pinned_root_owner_public_key(OWNER_TRUST)
                else:
                    key = self._test_key
                try:
                    started = datetime.fromisoformat(journal["started_at"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_START_TIME_INVALID") from exc
                approval = verify_exact_owner_release(
                    journal.get("signed_owner_proof"),
                    public_key=key,
                    expected_release_id=release_id(candidate),
                    expected_candidate_sha=candidate,
                    expected_rollback_sha=rollback,
                    expected_scope_sha256=manifest["scope_sha256"],
                    expected_manifest_sha256=digest(canonical(manifest)),
                    expected_freeze_sha256=manifest["freeze_sha256"],
                    at=started,
                )
                if approval["approval_id"] != journal.get("approval_id"):
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_APPROVAL_MISMATCH")
                before = journal.get("protected_before")
                if (
                    not isinstance(before, dict)
                    or set(before) != set(PROTECTED)
                    or not self._same_protected(before, self._verify_protected_snapshot())
                ):
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_PROTECTED_DRIFT")
                active_sha = self._active(component)
                if active_sha not in (None, rollback, candidate):
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_ACTIVE_DRIFT")
                observed = self.observe_component(manifest["compose_project"])
                if observed not in (None, rollback, candidate):
                    raise ComponentReleaseDenied("COMPONENT_RECOVERY_CONTAINER_DRIFT")
                previous = None if rollback == ZERO else releases / rollback
                if previous is not None:
                    prior = _load_json(trusted_file(
                        previous / "manifest.json", production=self.production,
                    ))
                    validate_manifest(prior)
                    if prior["candidate_sha"] != rollback or prior["component_id"] != component:
                        raise ComponentReleaseDenied("COMPONENT_RECOVERY_PRIOR_INVALID")
                    self._bundle(prior)
                self._freeze_bytes(manifest)
                with self.freeze_transaction(manifest["freeze_sha256"]):
                    self.restore_component(previous, manifest)
                    if self.observe_component(manifest["compose_project"]) != (
                        None if rollback == ZERO else rollback
                    ):
                        raise ComponentReleaseDenied("COMPONENT_RECOVERY_ROLLBACK_FAILED")
                    if self.verify_component(previous, manifest) is not True:
                        raise ComponentReleaseDenied("COMPONENT_RECOVERY_ACCEPTANCE_FAILED")
                    if not self._same_protected(before, self._verify_protected_snapshot()):
                        raise ComponentReleaseDenied("COMPONENT_RECOVERY_PROTECTED_CHANGED")
                self._freeze_bytes(manifest)
                active_path = active / (component + ".json")
                if rollback == ZERO and (active_path.exists() or active_path.is_symlink()):
                    if active_sha != candidate:
                        raise ComponentReleaseDenied("COMPONENT_RECOVERY_ACTIVE_POINTER_MISMATCH")
                    active_path.unlink()
                elif rollback != ZERO and active_sha == candidate:
                    _replace_json(active_path, {
                        "component_id": component,
                        "candidate_sha": rollback,
                        "manifest_sha256": digest(canonical(prior)),
                    })
                journal["state"] = "rolled_back"
                journal["reconciled"] = True
                journal["finished_at"] = datetime.now(timezone.utc).isoformat()
                _replace_json(path, journal)
                return {
                    "status": "component_rollback_verified",
                    "candidate_sha": candidate,
                    "rollback_sha": rollback,
                    "protected_services_changed": False,
                }
