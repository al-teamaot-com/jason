#!/usr/bin/env python3
"""Native host ports for the coordinated profile; source alone grants no authority.

The separately approved root installation must attest this module, its full
dependency closure, native helper, exact profile, source cache, shared control
readers and scheduled recovery. No operator-controlled checkout runs as root.
The original v1 request schema and authority remain unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
import ast
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shlex
import stat
import tempfile
import time
from typing import Mapping

from tools import scoped_backport_coordinated as co
from tools import scoped_backport_component_readback as readback
from implementation.kernel.signed_owner_release_v2 import (
    read_retired_release_policy, require_retired_release_mode,
    require_normal_deployment_enabled,
)
from tools.pmv4_host_release_guard import IndependentHostGuard
from tools.scoped_backport_native_host import (
    NativeScopedBackportHost, ROOT_STATE, CONTROL, DRIFT, FREEZE,
    TRUST_KEY, APPROVAL, exact_file, root_directory, root_json,
    atomic_root_json, run, source, utcnow,
)
from tools.scoped_backport_release import canonical, digest, deny, require_sha, require_hash
from implementation.kernel.signed_owner_release import read_pinned_root_owner_public_key

INSTALL = Path("/usr/local/lib/jason/scoped-backport")
INSTALLED = INSTALL / "tools/scoped_backport_coordinated_host.py"
POLICY = Path("/etc/jason-owner-release/scoped-backport-coordinated-installed.json")
PRIVATE = ROOT_STATE / "coordinated"
MANIFEST = PRIVATE / "manifest.json"
PROFILE = PRIVATE / "profile.json"
REPO = PRIVATE / "source.git"
NATIVE = INSTALL / "tools/coordinated_deploy_live_container.py"
DESIRED = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
READBACK = readback.READBACK
CONTROL_HELPER = INSTALL / "tools/scoped_backport_component_readback.py"
HEALTH = {
    "jason-runtime": (8080, "python"),
    "jason-mcp-pilot": (8000, "python"),
    "jason-teams-gateway": (3979, "node"),
}
RESOLVED = {"production_components_verified", "rollback_verified", "failed_before_mutation"}

# These exact paths are part of the independently reviewed installation.
# In particular, an installed host adapter without a native recovery dispatcher
# and migrated readers is NOT a production-eligible release path.
FILES = {
    "host": INSTALLED,
    "coordinator": INSTALL / "tools/scoped_backport_coordinated.py",
    "native_v1_host": INSTALL / "tools/scoped_backport_native_host.py",
    "native_v1_core": INSTALL / "tools/scoped_backport_release.py",
    "owner_proof": INSTALL / "implementation/kernel/signed_owner_release.py",
    "normal_owner_proof": INSTALL / "implementation/kernel/signed_owner_release_v2.py",
    "native_deploy": NATIVE,
    "native_projection": INSTALL / "tools/pmv4_mcp_projection.py",
    "readback": CONTROL_HELPER,
    "host_guard": INSTALL / "tools/pmv4_host_release_guard.py",
    "dispatch": INSTALL / "tools/scoped_backport_coordinated_root.py",
    "recovery_service": Path("/etc/systemd/system/jason-scoped-backport-recovery.service"),
    "recovery_timer": Path("/etc/systemd/system/jason-scoped-backport-recovery.timer"),
    "request_service": Path("/etc/systemd/system/jason-scoped-backport-requests.service"),
    "request_path": Path("/etc/systemd/system/jason-scoped-backport-requests.path"),
    "desired_state": DESIRED,
    "normal_request_dispatch": Path("/etc/systemd/system/jason-scoped-backport-requests.service.d/95-coordinated-normal-release.conf"),
    "normal_approval_watch": Path("/etc/systemd/system/jason-scoped-backport-requests.path.d/95-coordinated-normal-release.conf"),
    "normal_recovery_dispatch": Path("/etc/systemd/system/jason-scoped-backport-recovery.service.d/95-coordinated-normal-release.conf"),
}
POLICY_FIELDS = {
    "schema_version", "manifest_sha256", "profile_sha256", "source_sha",
    "file_sha256", "native_reader_migration_receipt_sha256",
}
MIGRATION = Path("/etc/jason-owner-release/coordinated-reader-migration.json")
MIGRATION_FIELDS = {
    "schema_version", "source_sha", "installed_readers", "native_readback_verified",
    "original_authority_preserved",
}
REUSABLE_POLICY_FIELDS = (POLICY_FIELDS - {"manifest_sha256", "profile_sha256"}) | {
    "allowed_targets", "per_release_review_required",
}
ACTIVE_OFFER_FIELDS = {"schema_version", "release_id", "offer_sha256"}
STAGED_OFFER_FIELDS = {"schema_version", "manifest", "profile", "review_source_sha", "eligibility"}
REQUIRED_READERS = {
    "pmv4_host_release_guard.py", "jason_self_heal_watchdog.py",
    "release_control_transition_worker.py",
}

MANAGER_ROOT = Path("/usr/local/lib/jason/pmv4-e-engineering-manager")
MANAGER_RECEIPT = Path("/etc/jason-owner-release/pmv4-e/engineering-manager-system-authorized.json")
MANAGER_GUARD = MANAGER_ROOT / "manager_guard.py"
WATCHDOG_LIVE = Path("/home/al/.local/lib/jason/jason_self_heal_watchdog.py")
TRANSITION_SUCCESSOR = INSTALL / "tools/release_control_transition_worker.py"


def trusted_directory(path: Path) -> None:
    for p in (path, *path.parents):
        m = p.lstat()
        if p.is_symlink() or not stat.S_ISDIR(m.st_mode) or m.st_uid != 0 or m.st_mode & 0o022:
            deny("COORDINATED_DIRECTORY_CUSTODY")


def trusted_bytes(path: Path, *, max_size: int = 1_000_000) -> bytes:
    trusted_directory(path.parent)
    return exact_file(path, uid=0, max_size=max_size)


def verify_effective_schedule() -> None:
    """The existing units must execute the reviewed fixed successor, not
    merely have installed source files. Preserve the original v1 ExecStart.
    """
    entry = str(FILES["dispatch"])
    for unit, field, path, action, timeout_value in (
        ("jason-scoped-backport-requests.service", "normal_request_dispatch",
         "/usr/local/lib/jason/scoped-backport/tools/scoped_backport_native_root.py", "promote-approved", "1h"),
        ("jason-scoped-backport-recovery.service", "normal_recovery_dispatch",
         "/usr/local/lib/jason/scoped-backport/tools/scoped_backport_native_recovery.py", "recover-scheduled", "30min"),
    ):
        values = {}
        raw = run("systemctl", "show", unit, "-p", "DropInPaths", "-p", "ExecStart",
                  "-p", "ExecStartPost", "-p", "ReadWritePaths", "-p", "TimeoutStartUSec", timeout=12).stdout.decode()
        for line in raw.splitlines():
            if "=" in line:
                k,v=line.split("=",1); values[k]=v
        if (values.get("DropInPaths","").split() != [str(FILES[field])]
                or path not in values.get("ExecStart","")
                or f"/usr/bin/python3 -I -B {entry} {action}" not in values.get("ExecStartPost","")
                or values.get("TimeoutStartUSec") != timeout_value
                or str(READBACK.parent) not in values.get("ReadWritePaths","").split()
                or "/etc/jason-owner-release" in values.get("ReadWritePaths","").split()
                or "/etc/jason-owner-release/normal-release-policy" in values.get("ReadWritePaths","").split()):
            deny("COORDINATED_EFFECTIVE_SCHEDULE_DRIFT")
    raw=run("systemctl","show","jason-scoped-backport-requests.path",
            "-p","DropInPaths","-p","Paths",timeout=12).stdout.decode()
    # systemd 255 emits one Paths= property per path specification.
    # Retain every row; require precisely the reviewed PathChanged watches.
    values = {}
    paths = []
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "Paths":
            paths.append(value)
        else:
            if key in values:
                deny("COORDINATED_EFFECTIVE_APPROVAL_WATCH_DRIFT")
            values[key] = value
    expected_paths = [
        "/var/lib/jason/authority/scoped-backport-release/requests (PathChanged)",
        "/var/lib/jason/authority/scoped-backport-release/owner-approvals (PathChanged)",
    ]
    if (values.get("DropInPaths","").split() != [str(FILES["normal_approval_watch"])]
            or sorted(paths) != sorted(expected_paths)):
        deny("COORDINATED_EFFECTIVE_APPROVAL_WATCH_DRIFT")
    trusted_directory(READBACK.parent)


def validate_staged_offer(value: Mapping) -> dict:
    if not isinstance(value, dict) or set(value) != STAGED_OFFER_FIELDS or value["schema_version"] != "3.0":
        deny("COORDINATED_STAGED_OFFER_SCHEMA")
    m = co.validate_manifest(value["manifest"])
    co.validate_profile(value["profile"], m)
    require_sha(value["review_source_sha"], "REVIEW_SOURCE")
    e = value["eligibility"]
    expected = {
        "schema_version": "3.0", "release_id": m["release_id"],
        "candidate_sha": m["candidate_sha"], "rollback_sha": m["rollback_sha"],
        "manifest_sha256": digest(m), "scope_sha256": m["scope_sha256"],
        "release_policy_sha256": m.get("release_policy_sha256"),
        "status": "native_coordinated_eligible_not_approved",
        "production_mutations": False, "provider_writes": False, "owner_approval_recorded": False,
    }
    if (m["schema_version"] != "3.0" or not isinstance(e, dict)
            or set(e) != set(expected) | {"observed_at"}
            or any(e[k] != v for k,v in expected.items())
            or not isinstance(e["observed_at"], str)):
        deny("COORDINATED_STAGED_ELIGIBILITY_SCOPE")
    return dict(value)


def active_staged_offer() -> dict | None:
    pointer = PRIVATE / "active-offer.json"
    if not os.path.lexists(pointer):
        return None
    row = root_json(pointer)
    if (set(row) != ACTIVE_OFFER_FIELDS or row["schema_version"] != "3.0"
            or not isinstance(row["release_id"], str)
            or not re.fullmatch(r"release-[0-9a-f]{16}", row["release_id"])):
        deny("COORDINATED_ACTIVE_OFFER_POINTER")
    require_hash(row["offer_sha256"], "ACTIVE_OFFER")
    root_directory(PRIVATE / "offers")
    offer = validate_staged_offer(root_json(PRIVATE / "offers" / (row["release_id"] + ".json"),
                                            max_size=2_000_000))
    if digest(offer) != row["offer_sha256"] or offer["manifest"]["release_id"] != row["release_id"]:
        deny("COORDINATED_ACTIVE_OFFER_DRIFT")
    return offer


def effective_reader_command(unit: str, *, user: str, argv: list[str]) -> None:
    raw = run("systemctl", "show", unit, "-p", "User", "-p", "ExecStart",
              timeout=12).stdout.decode()
    rows = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    # The effective command, not a similarly named installed file, is the
    # trusted reader. Reject extra commands and unexpected interpreters.
    commands = re.findall(r"argv\[\]=(.*?) ; ", rows.get("ExecStart", ""))
    if (rows.get("User") != user or len(commands) != 1
            or shlex.split(commands[0]) != argv):
        deny("COORDINATED_EFFECTIVE_READER_COMMAND_DRIFT")


def verified_manager_artifacts() -> dict:
    # Reuse the existing independently installed manager receipt and guard.
    # The active watchdog and development worker are UID1000 artifacts, not
    # root-owned files. The guard verifies their bytes against the immutable
    # root-owned copies and effective native unit topology.
    receipt = json.loads(trusted_bytes(MANAGER_RECEIPT))
    require_sha(receipt.get("candidate_sha"), "MANAGER_SOURCE")
    require_hash(receipt.get("guard_sha256"), "MANAGER_GUARD")
    if sha256(trusted_bytes(MANAGER_GUARD)).hexdigest() != receipt["guard_sha256"]:
        deny("COORDINATED_MANAGER_GUARD_DRIFT")
    result = run("runuser", "-u", "al", "--", "/usr/bin/python3", "-I", "-B",
                 str(MANAGER_GUARD), "--status", timeout=130)
    status = json.loads(result.stdout)
    if (status.get("status") != "verified_system_manager"
            or status.get("candidate_sha") != receipt["candidate_sha"]
            or status.get("operational_ready") is not True
            or status.get("production_authority") is not False):
        deny("COORDINATED_MANAGER_READBACK_DENIED")
    artifacts = status.get("artifact_sources")
    if not isinstance(artifacts, dict):
        deny("COORDINATED_MANAGER_ARTIFACTS_MISSING")
    expected_root = MANAGER_ROOT / "releases" / receipt["candidate_sha"] / "tools"
    checked = {}
    for name in ("jason_self_heal_watchdog.py", "owner_approved_development_worker.py"):
        row = artifacts.get(name)
        expected = (receipt.get("artifact_sha256") or {}).get(name)
        path = expected_root / name
        if (not isinstance(row, dict) or row.get("source") != str(path)
                or row.get("sha256") != expected
                or sha256(trusted_bytes(path)).hexdigest() != expected):
            deny("COORDINATED_MANAGER_ARTIFACT_DRIFT")
        checked[name] = (path, expected)
    return checked


def verify_reader_migration(migration: Mapping, policy: Mapping) -> None:
    if (set(migration) != MIGRATION_FIELDS or migration["schema_version"] != "2.0"
            or migration["source_sha"] != policy["source_sha"]
            or migration["native_readback_verified"] is not True
            or migration["original_authority_preserved"] is not True
            or not isinstance(migration["installed_readers"], list)):
        deny("COORDINATED_READER_MIGRATION_UNVERIFIED")
    artifacts = verified_manager_artifacts()
    watchdog, watchdog_sha = artifacts["jason_self_heal_watchdog.py"]
    worker, _ = artifacts["owner_approved_development_worker.py"]
    # The existing development worker independently pins its effective root
    # guard. Verify the reviewed static assignments in its attested source.
    values = {}
    for node in ast.parse(trusted_bytes(worker)).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key == "NATIVE_HEALTH_GUARD":
                if (not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name)
                        or node.value.func.id != "Path" or len(node.value.args) != 1
                        or node.value.keywords or key in values):
                    deny("COORDINATED_DEVELOPMENT_GUARD_BINDING")
                values[key] = ast.literal_eval(node.value.args[0])
            elif key == "NATIVE_HEALTH_GUARD_SHA256":
                if key in values:
                    deny("COORDINATED_DEVELOPMENT_GUARD_BINDING")
                values[key] = ast.literal_eval(node.value)
    guard = FILES["host_guard"]
    guard_sha = sha256(trusted_bytes(guard)).hexdigest()
    if (values.get("NATIVE_HEALTH_GUARD") != str(guard)
            or values.get("NATIVE_HEALTH_GUARD_SHA256") != guard_sha):
        deny("COORDINATED_DEVELOPMENT_GUARD_BINDING")
    expected = {
        str(guard): guard_sha,
        str(watchdog): watchdog_sha,
        str(TRANSITION_SUCCESSOR): sha256(trusted_bytes(TRANSITION_SUCCESSOR)).hexdigest(),
    }
    seen = {}
    for row in migration["installed_readers"]:
        if (not isinstance(row, dict) or set(row) != {"path", "sha256"}
                or row["path"] not in expected or row["path"] in seen
                or row["sha256"] != expected[row["path"]]):
            deny("COORDINATED_READER_INSTALLED_DRIFT")
        seen[row["path"]] = row["sha256"]
    if seen != expected:
        deny("COORDINATED_READER_MIGRATION_INCOMPLETE")
    effective_reader_command(
        "jason-self-heal-watchdog.service", user="al",
        argv=["/usr/bin/python3", "-B", str(WATCHDOG_LIVE), "--root",
              "/var/lib/jason/openclaw/self-heal", "--max-attempts", "2"],
    )
    for unit in ("jason-release-control-transition.service",
                 "jason-pmv4-component-transition.service"):
        effective_reader_command(
            unit, user="root",
            argv=["/usr/bin/python3", "-I", "-B", str(TRANSITION_SUCCESSOR)],
        )


def verify_installed_policy(profile: Mapping | None = None) -> dict:
    if os.geteuid() != 0 or Path(__file__).resolve(strict=True) != INSTALLED:
        deny("COORDINATED_IMMUTABLE_ROOT_INSTALL_REQUIRED")
    p = root_json(POLICY)
    if p.get("schema_version") == "2.0":
        if set(p) != POLICY_FIELDS or profile is None:
            deny("COORDINATED_ROOT_INSTALL_POLICY")
        require_hash(p["manifest_sha256"], "ROOT_MANIFEST")
        require_hash(p["profile_sha256"], "ROOT_PROFILE")
        if digest(profile) != p["profile_sha256"]:
            deny("COORDINATED_ROOT_PROFILE_DRIFT")
    elif p.get("schema_version") == "3.0":
        if (set(p) != REUSABLE_POLICY_FIELDS or p["allowed_targets"] != list(co.TARGET_ORDER)
                or p["per_release_review_required"] is not True):
            deny("COORDINATED_REUSABLE_INSTALL_POLICY")
        if profile is not None and (profile.get("schema_version") != "3.0"
                or not set(profile.get("allowed_targets", ())) <= set(p["allowed_targets"])):
            deny("COORDINATED_NORMAL_PROFILE_REQUIRED")
        root_directory(PRIVATE / "offers")
    else:
        deny("COORDINATED_ROOT_INSTALL_POLICY")
    require_sha(p["source_sha"], "ROOT_SOURCE")
    if set(p["file_sha256"]) != set(FILES):
        deny("COORDINATED_INSTALL_CLOSURE")
    for name, path in FILES.items():
        if sha256(trusted_bytes(path)).hexdigest() != p["file_sha256"][name]:
            deny("COORDINATED_INSTALLED_SOURCE_DRIFT")
    verify_effective_schedule()
    raw = trusted_bytes(MIGRATION)
    if sha256(raw).hexdigest() != p["native_reader_migration_receipt_sha256"]:
        deny("COORDINATED_READER_MIGRATION_DRIFT")
    migration = json.loads(raw)
    verify_reader_migration(migration, p)
    for unit in ("jason-scoped-backport-recovery.timer", "jason-scoped-backport-requests.path"):
        for verb, value in (("is-enabled", b"enabled"), ("is-active", b"active")):
            if run("systemctl", verb, unit, timeout=12).stdout.strip() != value:
                deny("COORDINATED_SCHEDULED_RECOVERY_UNAVAILABLE")
    for path in (PRIVATE, PRIVATE / "transactions", PRIVATE / "freeze-backups",
                 ROOT_STATE / "consumed-owner-approvals"):
        trusted_directory(path)
        root_directory(path)
    trusted_directory(REPO)
    read_pinned_root_owner_public_key(TRUST_KEY)
    return p


def inspect_container(name: str) -> dict | None:
    # Only exact production targets, protected peers, or deterministic retained
    # original names are accepted. Never accept an arbitrary user-supplied name.
    if name not in co.TARGET_ORDER + co.ALWAYS_PROTECTED and not re.fullmatch(
        r"(?:jason-runtime|jason-mcp-pilot|jason-teams-gateway)-rollback-scoped-[a-f0-9]{12}", name
    ):
        deny("COORDINATED_UNKNOWN_CONTAINER")
    # Distinguish actual absence from Docker daemon/query failure.
    names = run("docker", "ps", "-a", "--format", "{{.Names}}", timeout=15).stdout.decode().splitlines()
    if name not in names:
        return None
    rows = json.loads(run("docker", "inspect", "--type", "container", name, timeout=15).stdout)
    if len(rows) != 1 or rows[0].get("Name") != "/" + name:
        deny("COORDINATED_CONTAINER_CARDINALITY")
    return rows[0]


def required_container(name: str) -> dict:
    item = inspect_container(name)
    if item is None:
        deny("COORDINATED_CONTAINER_MISSING")
    return item


def config_fingerprint(item: Mapping) -> str:
    """Compare configuration without writing environment secrets to receipts."""
    c, h = item["Config"], item["HostConfig"]
    values = {}
    for entry in c.get("Env") or []:
        key, sep, value = entry.partition("=")
        if not sep or key in values:
            deny("COORDINATED_ENVIRONMENT_AMBIGUOUS")
        values[key] = value
    values.pop("JASON_SOURCE_REVISION", None)
    # Retain the prior security settings, identities, networks and all mounts.
    return digest({
        "environment": values,
        "config": {k:c.get(k) for k in ("User","WorkingDir","Entrypoint","Cmd","Healthcheck")},
        "host": {k:h.get(k) for k in ("ReadonlyRootfs","Privileged","CapDrop","CapAdd",
                   "SecurityOpt","Memory","NanoCpus","PidsLimit","NetworkMode","RestartPolicy",
                   "PortBindings","Devices","Tmpfs","PidMode","IpcMode")},
        "mounts": sorted((m["Type"], m["Source"], m["Destination"], m["RW"])
                         for m in item.get("Mounts") or []),
        "networks": sorted(item.get("NetworkSettings", {}).get("Networks", {})),
    })


def exact_original(item: Mapping, target: Mapping) -> bool:
    return (item.get("Id") == target["rollback_container_id"]
            and item.get("Image") == target["rollback_image"]
            and source(item) == target["rollback_revision"])


def assert_healthy(item: Mapping, name: str) -> None:
    state = item["State"]
    health = (state.get("Health") or {}).get("Status")
    if not state.get("Running") or state.get("Status") != "running" or health not in (None, "healthy"):
        deny("COORDINATED_TARGET_UNHEALTHY")
    if name in ("jason-runtime", "jason-pmv4-ticket-core") and health != "healthy":
        deny("COORDINATED_REQUIRED_HEALTH_MISSING")


def peer_snapshot(item: Mapping, name: str) -> dict:
    s, h = item["State"], item["HostConfig"]
    if name == co.SHADOW and not s["Running"]:
        labels = item["Config"].get("Labels") or {}
        mounts = item.get("Mounts") or []
        # Exact existing nonproduction OOM exception; a stopped real production
        # peer, or a different non-isolated shadow, is never waived.
        if (s.get("Status") != "exited" or s.get("OOMKilled") is not True
                or s.get("ExitCode") != 137 or s.get("Pid") != 0
                or item.get("RestartCount") != 0 or h.get("NetworkMode") != "none"
                or h.get("ReadonlyRootfs") is not True or h.get("Privileged") is not False
                or "ALL" not in (h.get("CapDrop") or []) or h.get("CapAdd")
                or "no-new-privileges:true" not in (h.get("SecurityOpt") or [])
                or h.get("PortBindings") or h.get("Devices")
                or h.get("Memory") != 4294967296 or h.get("NanoCpus") != 1000000000
                or h.get("PidsLimit") != 256
                or item.get("Image") != "sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd"
                or h.get("RestartPolicy", {}).get("Name") != "no"
                or len(mounts) != 1 or mounts[0].get("Type") != "volume"
                or mounts[0].get("Destination") != "/home/node/.openclaw"
                or labels.get("com.aot.jason.source_revision") != "75f2b4c0c48a15bd17d700b9f039fe56623e3f52"):
            deny("COORDINATED_SHADOW_NOT_EXACT_ISOLATED_OOM")
    else:
        assert_healthy(item, name)
    return {"id": item["Id"], "image": item["Image"], "started_at": s["StartedAt"],
            "running": s["Running"], "status": s["Status"], "oom": s.get("OOMKilled"),
            "configuration_sha256": config_fingerprint(item)}


def publish_readback(value: Mapping | None, previous: Mapping | None) -> None:
    # Compare-and-replace with a root-only writer under both release locks.
    trusted_directory(READBACK.parent)
    if readback.read() != previous:
        deny("COORDINATED_READBACK_CONCURRENT_CHANGE")
    if value is None:
        if previous is not None:
            READBACK.unlink()
    else:
        readback.validate(value)
        fd, temp = tempfile.mkstemp(prefix=".coordinated-readback-", dir=READBACK.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(canonical(value))
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temp, 0o644)
            os.replace(temp, READBACK)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    fd = os.open(READBACK.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class CoordinatedHost(NativeScopedBackportHost):
    """Existing native transaction ports specialized by exact root profile."""

    def __init__(self):
        super().__init__(repo=REPO, root=PRIVATE)
        self.guard = None
        self.active_profile = None
        self.active_review_sha = None
        self._staging = False

    def enforce_installed_root_trust(self, profile: Mapping) -> None:
        self._staging = False
        self.policy = verify_installed_policy(profile)
        if self.policy["schema_version"] == "3.0":
            offer = active_staged_offer()
            if offer is None or offer["profile"] != dict(profile):
                deny("COORDINATED_ROOT_STAGED_OFFER_REQUIRED")
            m = co.validate_manifest(offer["manifest"])
            self.active_review_sha = offer["review_source_sha"]
        else:
            m = co.validate_manifest(root_json(MANIFEST))
            if digest(m) != self.policy["manifest_sha256"]:
                deny("COORDINATED_INSTALLED_MANIFEST_DRIFT")
            self.active_review_sha = self.policy["source_sha"]
        self.active_profile = co.validate_profile(profile, m)
        self.active_offer = m

    def bind_for_stage(self, manifest: Mapping, profile: Mapping, review_source_sha: str) -> None:
        # This is a read-only admission operation, not a promotion or a
        # production authority grant. All new scope bytes are independently
        # verified under the existing shared locks before eligibility exists.
        self.policy = verify_installed_policy(profile)
        if self.policy["schema_version"] != "3.0":
            deny("COORDINATED_REUSABLE_NATIVE_INSTALL_REQUIRED")
        m = co.validate_manifest(manifest)
        if m["schema_version"] != "3.0":
            deny("COORDINATED_NORMAL_PROFILE_REQUIRED")
        require_sha(review_source_sha, "REVIEW_SOURCE")
        self.active_offer = m
        self.active_profile = co.validate_profile(profile, m)
        self.active_review_sha = review_source_sha
        self._staging = True

    def _require_root_trust(self) -> None:
        if (self.policy is None or os.geteuid() != 0
                or Path(__file__).resolve(strict=True) != INSTALLED):
            deny("COORDINATED_IMMUTABLE_ROOT_INSTALL_REQUIRED")

    def _bound(self, manifest: Mapping) -> None:
        self._require_root_trust()
        if self.active_offer != dict(manifest):
            deny("COORDINATED_UNBOUND_MANIFEST")

    def _target(self, m: Mapping, t: Mapping) -> None:
        self._bound(m)
        if dict(t) not in m["targets"]:
            deny("COORDINATED_UNBOUND_TARGET")

    @contextmanager
    def release_lock(self, manifest: Mapping):
        self._bound(manifest)
        self.guard = IndependentHostGuard()
        try:
            with self.guard.host_release_transaction():
                yield
        finally:
            self.guard = None

    def _locked(self) -> None:
        self._require_root_trust()
        if self.guard is None or not self.guard._held:
            deny("COORDINATED_SHARED_LOCK_REQUIRED")

    def _require_current_staged_scope(self) -> None:
        if (self.policy or {}).get("schema_version") != "3.0" or self._staging:
            return
        row = active_staged_offer()
        if (row is None or row["manifest"] != self.active_offer
                or row["profile"] != self.active_profile
                or row["review_source_sha"] != self.active_review_sha):
            deny("COORDINATED_ACTIVE_OFFER_CHANGED_UNDER_LOCK")

    def _args(self, m: Mapping, t: Mapping) -> list[str]:
        self._target(m, t)
        name = t["name"]
        port, runtime = HEALTH[name]
        # Isolated Python deliberately excludes the script directory. Import
        # only the exact attested root package so the helper's sibling import
        # works without trusting PYTHONPATH or the caller's checkout.
        bootstrap = ("import runpy,sys;sys.path.insert(0,"
                     + repr(str(INSTALL)) + ");"
                     "runpy.run_module('tools.coordinated_deploy_live_container',run_name='__main__')")
        return ["/usr/bin/python3", "-I", "-B", "-c", bootstrap, "--live", name,
                "--image", t["candidate_image"],
                "--rollback", self._rollback_name(name, m),
                "--source-revision", m["projections"][t["projection"]]["candidate_sha"],
                "--health-url", f"http://127.0.0.1:{port}/healthz", "--health-runtime", runtime]

    def _frozen(self, manifest: Mapping) -> dict:
        """Revalidate the exact current policy; never retire a marker here."""
        policy = read_retired_release_policy()
        if manifest["schema_version"] == "3.0":
            if policy is None or policy != manifest["release_policy_sha256"]:
                deny("COORDINATED_NORMAL_POLICY_DRIFT")
            require_retired_release_mode(FREEZE.parent, policy)
            return {"release_policy_sha256": policy}
        if policy is not None:
            deny("COORDINATED_LEGACY_SCOPE_AFTER_RETIREMENT")
        return super()._frozen(manifest)

    def freshly_validate_live_scope(self, manifest: Mapping) -> None:
        self._bound(manifest)
        self._locked()
        self._require_current_staged_scope()
        profile = self.active_profile
        if profile is None or self.active_review_sha is None:
            deny("COORDINATED_UNBOUND_REVIEW")
        if manifest["schema_version"] == "3.0":
            # A previous candidate's local cache must not make every later
            # protected-main merge require another privileged installation.
            trusted_directory(self.repo)
            origin = co._git(self.repo, "remote", "get-url", "origin").decode().strip()
            if origin != "https://github.com/al-teamaot-com/jason.git":
                deny("COORDINATED_ROOT_CACHE_ORIGIN")
            if co._git(self.repo, "rev-parse", "--is-bare-repository").strip() != b"true":
                deny("COORDINATED_ROOT_CACHE_NOT_BARE")
            refs = sorted({p["snapshot_ref"] for p in manifest["projections"].values()})
            if any(not re.fullmatch(r"refs/heads/prep/[a-z0-9-]{5,100}", ref) for ref in refs):
                deny("COORDINATED_ROOT_CACHE_REF")
            run("/usr/bin/git", "-C", str(self.repo), "-c", "core.hooksPath=/dev/null",
                "-c", "protocol.file.allow=never", "fetch", "--no-tags",
                "--no-recurse-submodules", "origin",
                "+refs/heads/main:refs/remotes/origin/main",
                *["+"+ref+":"+ref for ref in refs], timeout=180)
        co.source_admission(self.repo, manifest, profile)
        # The root-pinned installation SHA and exact private manifest digest
        # must also have protected-main review, not just the feature projection.
        head = co._git(self.repo, "ls-remote", "origin", "refs/heads/main").decode().split()[0]
        if not co._ancestor(self.repo, self.policy["source_sha"], head):
            deny("COORDINATED_INSTALL_SOURCE_NOT_PROTECTED_MAIN")
        if (not co._ancestor(self.repo, self.active_review_sha, head)
                or not co._ancestor(self.repo, manifest["protected_main_sha"], self.active_review_sha)):
            deny("COORDINATED_SCOPE_REVIEW_NOT_PROTECTED_MAIN")
        review = json.loads(co._git(self.repo, "show", self.active_review_sha +
                                   ":config/coordinated-scoped-release-review.json"))
        if (review.get("manifest_sha256") != digest(manifest)
                or review.get("scope_sha256") != manifest["scope_sha256"]
                or review.get("profile") != manifest["profile"]
                or review.get("candidate_sha") != manifest["candidate_sha"]
                or review.get("schema_version") != manifest["schema_version"]
                or review.get("production_authority") is not False):
            deny("COORDINATED_PRIVATE_MANIFEST_NOT_REVIEWED")
        self.freeze_before = self._frozen(manifest)
        if manifest["schema_version"] == "3.0":
            require_normal_deployment_enabled(FREEZE.parent, manifest["release_policy_sha256"])
        self.previous_readback = readback.verify_live()
        self.original_components = readback.inspect_components()
        self.original_configs = {}
        for t in manifest["targets"]:
            name = t["name"]
            item = required_container(name)
            if not exact_original(item, t) or inspect_container(self._rollback_name(name, manifest)) is not None:
                deny("COORDINATED_ORIGINAL_IDENTITY_OR_RETAINED_NAME")
            assert_healthy(item, name)
            self.original_configs[name] = config_fingerprint(item)
            for key, rev in (("candidate_image", manifest["projections"][t["projection"]]["candidate_sha"]),
                             ("rollback_image", t["rollback_revision"])):
                image = json.loads(run("docker", "image", "inspect", t[key], timeout=15).stdout)
                if (len(image) != 1 or image[0]["Id"] != t[key]
                        or image[0]["Config"]["Labels"].get("org.opencontainers.image.revision") != rev):
                    deny("COORDINATED_IMAGE_SOURCE_DRIFT")
            probe = run(*self._args(manifest, t), "--preflight", timeout=90, allow_failure=True)
            if probe.returncode or b"PREFLIGHT=PASS" not in probe.stdout:
                deny("COORDINATED_NATIVE_PREFLIGHT_FAILED")

    def ensure_breaker_closed_and_workers_quiescent(self) -> None:
        self._locked()
        m = self.active_offer
        ctl, drift = root_json(CONTROL), root_json(DRIFT)
        baseline = (ctl.get("last_known_good") or {}).get("manifest") or {}
        if (ctl.get("circuit_breaker", {}).get("state") != "closed"
                or drift.get("status") != "pass" or drift.get("problems")
                or baseline.get("complete") is not True
                or baseline.get("host_revision") != readback.HOST_CURRENT.resolve(strict=True).name
                or not self.guard.host_mutation_quiescent()):
            deny("COORDINATED_PROTECTED_CONTROL")
        if self.previous_readback is not None:
            readback.verify_legacy_anchor(self.previous_readback, baseline)
        elif any(self.original_components[n]["revision"] != baseline.get("revision")
                 or self.original_components[n]["image_id"] != baseline.get(key)
                 for n, key in (("jason-runtime","runtime_image_id"),
                                ("jason-mcp-pilot","mcp_image_id"))):
            deny("COORDINATED_UNATTESTED_BASELINE")
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))).total_seconds()
        if not 0 <= age <= 180:
            deny("COORDINATED_DRIFT_STALE")
        desired = json.loads(trusted_bytes(DESIRED))
        prefixes = desired["rollback_container_prefixes"]
        maximum = desired["max_stopped_rollback_containers"]
        names = run("docker", "ps", "-a", "--filter", "status=exited", "--format", "{{.Names}}",
                    timeout=15).stdout.decode().splitlines()
        # Capacity is not increased, and unrelated retained originals are never deleted.
        if (not isinstance(maximum, int)
                or any(not self._rollback_name(t["name"], m).startswith(tuple(prefixes)) for t in m["targets"])
                or sum(n.startswith(tuple(prefixes)) for n in names) + len(m["targets"]) > maximum):
            deny("COORDINATED_ROLLBACK_CAPACITY")
        self.snapshot_protected()
        self.host_anchor = baseline["host_revision"]

    def deny_unresolved_attempt(self, manifest: Mapping) -> None:
        self._bound(manifest)
        for path in (ROOT_STATE / "transactions").glob("release-*.json"):
            if root_json(path).get("outcome") not in {
                "production_pair_verified", "rollback_verified", "failed_before_mutation"
            }:
                deny("COORDINATED_LEGACY_UNRESOLVED_ATTEMPT")
        for path in self.root.joinpath("transactions").glob("release-*.json"):
            if path == self._journal_path(manifest) or root_json(path).get("outcome") not in RESOLVED:
                deny("COORDINATED_PRIOR_ATTEMPT")

    def consumed_approvals(self) -> frozenset[str]:
        folder = ROOT_STATE / "consumed-owner-approvals"
        root_directory(folder)
        ids = []
        for file in folder.iterdir():
            if file.suffix != ".json" or not APPROVAL.fullmatch(file.stem):
                deny("COORDINATED_CONSUMPTION_LEDGER")
            root_json(file, max_size=4096)
            ids.append(file.stem)
        return frozenset(ids)

    def consume_owner_proof(self, approval_id: str) -> None:
        self._locked()
        if not APPROVAL.fullmatch(approval_id) or approval_id in self.consumed_approvals():
            deny("COORDINATED_OWNER_APPROVAL_REPLAY")
        atomic_root_json(ROOT_STATE / "consumed-owner-approvals" / (approval_id + ".json"), {
            "schema_version":"2.0", "approval_id":approval_id,
            "release_id":self.active_offer["release_id"], "consumed_at":utcnow(), "one_use":True,
        })
        self._journal_update(self.active_offer, "one_use_owner_proof_consumed")

    def snapshot_protected(self) -> dict:
        self._require_root_trust()
        return {name: peer_snapshot(required_container(name), name)
                for name in self.active_offer["protected_services"]}

    def record_intent(self, manifest: Mapping, decision: Mapping, protected: Mapping) -> None:
        self._bound(manifest)
        self._locked()
        atomic_root_json(self._journal_path(manifest), {
            "schema_version":"2.0", "manifest_sha256":digest(manifest),
            "release_id":manifest["release_id"], "scope_sha256":manifest["scope_sha256"],
            "approval_id":decision["approval_id"], "protected_before":protected,
            "original_configs":self.original_configs, "original_components":self.original_components,
            "previous_readback":self.previous_readback, "host_anchor":self.host_anchor,
            "mutation_attempted":False, "status":"intent_durable_no_mutation", "created_at":utcnow(),
        })

    @contextmanager
    def frozen_transaction(self, manifest: Mapping, decision: Mapping):
        self._bound(manifest)
        self._locked()
        if decision["approval_id"] not in self.consumed_approvals() or self._frozen(manifest) != self.freeze_before:
            deny("COORDINATED_FROZEN_TRANSACTION_NOT_AUTHORIZED")
        if manifest["schema_version"] == "3.0":
            require_normal_deployment_enabled(FREEZE.parent, manifest["release_policy_sha256"])
        # A scoped signed exception uses the exact native helper under both
        # shared locks. The global freeze file stays active throughout; there
        # is no window in which legacy or another release becomes authorized.
        self._journal_update(manifest, "exact_signed_normal_policy_scope" if manifest["schema_version"] == "3.0"
                             else "exact_signed_scope_under_active_freeze")
        try:
            yield
        finally:
            self._frozen(manifest)
            self._journal_update(manifest, "normal_policy_preserved_pending_verify" if manifest["schema_version"] == "3.0"
                                 else "freeze_preserved_pending_verify")

    def promote_exact_target(self, m: Mapping, t: Mapping) -> None:
        self._target(m, t)
        self._locked()
        self._frozen(m)
        if m["schema_version"] == "3.0":
            require_normal_deployment_enabled(FREEZE.parent, m["release_policy_sha256"])
        journal = self._journal(m)
        if (journal["approval_id"] not in self.consumed_approvals()
                or not exact_original(required_container(t["name"]), t)
                or config_fingerprint(required_container(t["name"])) != journal["original_configs"][t["name"]]):
            deny("COORDINATED_PREMUTATION_BASELINE_CHANGED")
        self._journal_update(m, "mutating_" + t["name"].replace("-", "_"), mutation_attempted=True)
        result = run(*self._args(m, t), timeout=480, allow_failure=True)
        if result.returncode or b"DEPLOYMENT=PASS" not in result.stdout:
            deny("COORDINATED_NATIVE_REPLACEMENT_FAILED")
        item = required_container(t["name"])
        retained = required_container(self._rollback_name(t["name"], m))
        if not exact_original(retained, t):
            deny("COORDINATED_RETAINED_ORIGINAL_DRIFT")
        if item["Image"] != t["candidate_image"] or source(item) != m["projections"][t["projection"]]["candidate_sha"]:
            deny("COORDINATED_REPLACEMENT_IDENTITY_NOT_EXACT")
        ids = dict(self._journal(m).get("candidate_ids", {}))
        ids[t["name"]] = item["Id"]
        self._journal_update(m, "candidate_identity_durable", candidate_ids=ids)
        self._wait_candidate_ready(m, t, item)
        self._journal_update(m, "component_replacement_verified")

    def _verify_candidate_identity(self, m: Mapping, t: Mapping, item: Mapping) -> None:
        name = t["name"]
        journal = self._journal(m)
        if (item["Id"] != journal["candidate_ids"].get(name)
                or item["Image"] != t["candidate_image"]
                or source(item) != m["projections"][t["projection"]]["candidate_sha"]
                or config_fingerprint(item) != journal["original_configs"][name]):
            deny("COORDINATED_CANDIDATE_OR_CONFIGURATION_DRIFT")

    def _wait_candidate_ready(self, m: Mapping, t: Mapping, item: Mapping) -> None:
        # The deploy helper has passed the HTTP health probe. Docker's own
        # health check runs on a separate schedule and can still be starting.
        started_at = item["State"]["StartedAt"]
        deadline = time.monotonic() + 60
        while True:
            self._verify_candidate_identity(m, t, item)
            state = item["State"]
            if state["StartedAt"] != started_at:
                deny("COORDINATED_CANDIDATE_RESTARTED_DURING_READINESS")
            health = (state.get("Health") or {}).get("Status")
            if not (state["Running"] and state["Status"] == "running" and health == "starting"):
                assert_healthy(item, t["name"])
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                deny("COORDINATED_CANDIDATE_READINESS_TIMEOUT")
            time.sleep(min(2, remaining))
            item = required_container(t["name"])

    def _verify_candidate(self, m: Mapping, t: Mapping, item: Mapping) -> None:
        self._verify_candidate_identity(m, t, item)
        assert_healthy(item, t["name"])

    def verify_candidate_targets(self, m: Mapping) -> None:
        for t in m["targets"]:
            self._verify_candidate(m, t, required_container(t["name"]))

    def publish_component_readback(self, m: Mapping, decision: Mapping) -> None:
        self._bound(m)
        self._locked()
        self.verify_candidate_targets(m)
        journal = self._journal(m)
        value = readback.validate({
            "schema_version":m["schema_version"], "status":"verified_component_release",
            "host_revision":journal["host_anchor"], "release_id":m["release_id"],
            "manifest_sha256":digest(m), "scope_sha256":m["scope_sha256"],
            **co.binding(m), "components":readback.inspect_components(),
        })
        # Record proposed readback durably BEFORE publication; recovery can
        # restore the exact prior state if interrupted during publication.
        self._journal_update(m, "component_readback_prepared", proposed_readback=value)

    def verify_component_readback(self, m: Mapping, *, frozen: bool) -> None:
        self._bound(m)
        self._locked()
        self._frozen(m)
        journal = self._journal(m)
        value = journal["proposed_readback"]
        readback.verify(value, readback.inspect_components(),
                        host_revision=readback.HOST_CURRENT.resolve(strict=True).name,
                        **co.binding(m))
        if frozen:
            publish_readback(value, journal["previous_readback"])
            if readback.verify_live() != value:
                deny("COORDINATED_PUBLISHED_READBACK_DRIFT")
            # Exercise the installed readback path, not a hypothetical source-only reader.
            result = run("runuser", "-u", "al", "--", "/usr/bin/python3", "-I", "-B",
                         str(CONTROL_HELPER), "--capture-native-health", timeout=90)
            actual = json.loads(result.stdout)
            baseline = root_json(CONTROL)["last_known_good"]["manifest"]
            readback.verify_host_fingerprint(baseline, actual, value)

    def restore_exact_target(self, m: Mapping, t: Mapping) -> None:
        self._target(m, t)
        self._locked()
        name = t["name"]
        retained_name = self._rollback_name(name, m)
        current, retained = inspect_container(name), inspect_container(retained_name)
        if current is not None and exact_original(current, t):
            if retained is not None:
                deny("COORDINATED_AMBIGUOUS_ORIGINAL")
            if not current["State"]["Running"]:
                run("docker", "start", name, timeout=90)
            return
        if retained is None or not exact_original(retained, t):
            deny("COORDINATED_ROLLBACK_ORIGINAL_NOT_EXACT")
        if current is not None:
            if (current["Image"] != t["candidate_image"]
                    or source(current) != m["projections"][t["projection"]]["candidate_sha"]):
                deny("COORDINATED_FOREIGN_CONTAINER_NO_ROLLBACK_MUTATION")
            journal = self._journal(m)
            expected_id = journal.get("candidate_ids", {}).get(name)
            if expected_id is not None:
                if current["Id"] != expected_id:
                    deny("COORDINATED_REPLACEMENT_ID_DRIFT")
            elif config_fingerprint(current) != journal["original_configs"][name]:
                deny("COORDINATED_INTERRUPTED_CANDIDATE_UNVERIFIED")
            run("docker", "rm", "-f", name, timeout=90)
        run("docker", "rename", retained_name, name, timeout=30)
        run("docker", "start", name, timeout=90)

    def verify_rollback(self, m: Mapping) -> None:
        self._bound(m)
        journal = self._journal(m)
        for t in m["targets"]:
            item = required_container(t["name"])
            if not exact_original(item, t) or config_fingerprint(item) != journal["original_configs"][t["name"]]:
                deny("COORDINATED_ROLLBACK_IDENTITY_DRIFT")
            # Same health endpoint/runtime as native deploy, bounded.
            port, runtime = HEALTH[t["name"]]
            if runtime == "python":
                code = "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:%d/healthz',timeout=3).status==200" % port
                probe = ["python", "-c", code]
            else:
                code = "fetch('http://127.0.0.1:%d/healthz',{signal:AbortSignal.timeout(3000)}).then(r=>{if(r.status!==200)process.exit(1)}).catch(()=>process.exit(1))" % port
                probe = ["node", "-e", code]
            for _ in range(30):
                if run("docker", "exec", t["name"], *probe, timeout=8, allow_failure=True).returncode == 0:
                    try:
                        assert_healthy(required_container(t["name"]), t["name"])
                        break
                    except PermissionError:
                        pass
                time.sleep(2)
            else:
                deny("COORDINATED_ROLLBACK_HEALTH_UNVERIFIED")

    def clear_component_readback(self, m: Mapping) -> None:
        journal = self._journal(m)
        actual = readback.read()
        previous = journal["previous_readback"]
        if actual == previous:
            return
        if actual != journal.get("proposed_readback"):
            deny("COORDINATED_FOREIGN_READBACK_NO_ROLLBACK_MUTATION")
        publish_readback(previous, actual)

    def verify_freeze_restored(self, manifest: Mapping) -> None:
        self._bound(manifest)
        self._frozen(manifest)
        self._journal_update(manifest, "normal_policy_preserved_verified" if manifest["schema_version"] == "3.0"
                             else "freeze_preserved_verified")

    def record_outcome(self, m: Mapping, outcome: str, error: str = "") -> None:
        self._bound(m)
        self._locked()
        if outcome not in RESOLVED | {"rollback_unverified","recovery_required"}:
            deny("COORDINATED_UNKNOWN_OUTCOME")
        self._journal_update(m, "outcome_recorded", outcome=outcome, failure_class=error[:120])

    def recover(self, m: Mapping) -> dict:
        """Crash recovery only; never promotes or closes a breaker."""
        self._bound(m)
        with self.release_lock(m):
            self._require_current_staged_scope()
            journal = self._journal(m)
            if journal["manifest_sha256"] != digest(m) or journal["scope_sha256"] != m["scope_sha256"]:
                deny("COORDINATED_RECOVERY_SCOPE")
            if journal.get("outcome") in RESOLVED:
                return {"status":"resolved_prior_attempt_no_action"}
            self.open_breaker("SCOPED_BACKPORT_COORDINATED_INTERRUPTED_TRANSACTION")
            if journal.get("mutation_attempted"):
                if journal["approval_id"] not in self.consumed_approvals():
                    deny("COORDINATED_RECOVERY_NO_CONSUMED_PROOF")
                for t in reversed(m["targets"]):
                    self.restore_exact_target(m,t)
                self.verify_rollback(m)
                self.clear_component_readback(m)
            self.verify_protected_unchanged(journal["protected_before"])
            self.verify_freeze_restored(m)
            self.record_outcome(m,"rollback_verified" if journal.get("mutation_attempted") else "failed_before_mutation")
            return {"status":"interrupted_rollback_verified_breaker_open"}
