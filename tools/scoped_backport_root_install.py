#!/usr/bin/env python3
"""One-time Owner-authenticated, protected-main source-pinned scoped release installer.

This installs ONLY native release-control code and disabled-by-default root
request/recovery service plumbing. It NEVER swaps running runtime/MCP images,
unfreezes production, grants Graph permissions, or signs a production release.

--check: source-only validation, no sudo or mutation.
--apply: requires authenticated local 'al' sudo AND fresh Entra OAuth Owner
sign-in + affirmative exact SHA/scope decision before ANY privileged mutation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
SOURCE_CACHE = Path("/home/al/.local/lib/jason/engineering-source-repo")
sys.path.insert(0, str(REPO))


class ScopedInstallDenied(PermissionError):
    pass


def deny(code: str) -> None:
    raise ScopedInstallDenied("SCOPED_BACKPORT_" + code)

INSTALL_ROOT = Path("/usr/local/lib/jason/scoped-backport")
ROOT_POLICY = Path("/etc/jason-owner-release/scoped-backport-installed.json")
ROOT_PUBLIC_ATTEST = Path("/etc/jason-owner-release/scoped-backport-public-attestation.json")
ROOT_STATE = Path("/var/lib/jason-scoped-backport")
PUBLIC = Path("/var/lib/jason/authority/scoped-backport-release")
LEDGER = Path("/etc/jason-owner-release/scoped-backport-install-ledger")
SERVICES = Path("/etc/systemd/system")
VERIFIER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
VERIFIER_HASH = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
ORIGINAL_PROTECTED = (
    "jason-runtime", "jason-mcp-pilot", "jason-pmv4-ticket-core",
    "jason-pmv4-shadow-gateway", "openbao", "jason-teams-gateway",
)
FILES = (
    "tools/scoped_backport_native_root.py",
    "tools/scoped_backport_native_host.py",
    "tools/scoped_backport_release.py",
    "tools/scoped_backport_release_request.py",
    "tools/scoped_backport_native_recovery.py",
    "tools/scoped_backport_owner_local_approval.py",
    "tools/deploy_live_container.py",
    # deploy_live_container.py imports this root-owned sibling at module load.
    "tools/pmv4_mcp_projection.py",
    "implementation/kernel/signed_owner_release.py",
    "implementation/kernel/__init__.py",
)
UNITS = (
    "jason-scoped-backport-recovery.service",
    "jason-scoped-backport-recovery.timer",
    "jason-scoped-backport-requests.service",
    "jason-scoped-backport-requests.path",
)
UNIT_DIR = Path("infrastructure/scoped-backport-release")
ROOT_DIRS = (
    "transactions", "consumed-owner-approvals", "freeze-backups",
    "offers", "requests",
)
PUBLIC_DIRS = (
    "requests", "processed", "offers", "eligibility", "owner-approvals",
    "results",
)
REGEX_SHA = re.compile(r"^[0-9a-f]{40}$")
REGEX_HASH = re.compile(r"^[0-9a-f]{64}$")
ACTION = "INSTALL-EXACT-SCOPED-BACKPORT-ROOT-V1"


def git(*args: str) -> bytes:
    p = subprocess.run(["git", "-c", f"safe.directory={REPO}",
                        "-C", str(REPO), *args],
                       capture_output=True, check=False, timeout=30)
    if p.returncode:
        deny("INSTALL_PROTECTED_GIT_UNAVAILABLE")
    return p.stdout


def source_tree(sha: str, reviewed_ci_sha: str) -> dict[str, bytes]:
    if not REGEX_SHA.fullmatch(sha) or not REGEX_SHA.fullmatch(reviewed_ci_sha):
        deny("INSTALL_SOURCE_OR_REVIEWED_SHA_INVALID")
    actual = git("rev-parse", "HEAD").decode().strip()
    dirty = git("status", "--porcelain").strip()
    if actual != sha or dirty:
        deny("INSTALL_SOURCE_NOT_CLEAN_EXACT_SHA")
    remote = git("ls-remote", "origin", "refs/heads/main").decode().strip().split()
    if remote != [sha, "refs/heads/main"]:
        deny("INSTALL_SOURCE_NOT_LATEST_PROTECTED_MAIN")
    if not (REPO / "tools/scoped_backport_release.py").is_file():
        deny("INSTALL_REQUIRED_MODULE_MISSING")
    result = {}
    for name in FILES + tuple((UNIT_DIR / k).as_posix() for k in UNITS):
        if (REPO / name).is_symlink():
            deny("INSTALL_SOURCE_SYMLINK")
        blob = git("show", sha + ":" + name)
        tested = git("show", reviewed_ci_sha + ":" + name)
        if blob != tested:
            deny("INSTALL_REVIEWED_CI_TO_MAIN_SOURCE_DRIFT")
        if len(blob) > 400_000:
            deny("INSTALL_SOURCE_EXCESS_SIZE")
        if name.endswith(".py") and blob:
            compile(blob, name, "exec")
        if (REPO / name).read_bytes() != blob:
            deny("INSTALL_SOURCE_BLOB_DIFFERENT")
        result[name] = blob
    # The operator executes this bootstrap directly from the clean main
    # worktree. Bind its own executable bytes to the exact CI-reviewed SHA
    # too, without installing an additional privileged bootstrap copy.
    installer_path = "tools/scoped_backport_root_install.py"
    main_installer = git("show", sha + ":" + installer_path)
    reviewed_installer = git("show", reviewed_ci_sha + ":" + installer_path)
    if (main_installer != reviewed_installer
            or (REPO / installer_path).read_bytes() != main_installer):
        deny("INSTALLER_REVIEWED_CI_SOURCE_MISMATCH")
    # Audit-only: the imported package has now been byte-verified against
    # the immutable protected-main Git object before executing module code.
    from tools.scoped_backport_release import source_admission
    source_admission(REPO, trusted_main_sha=sha)
    verified_release_objects_available(sha, reviewed_ci_sha)
    required_github_checks(reviewed_ci_sha)
    return result


def verified_release_objects_available(sha: str, reviewed_ci_sha: str) -> None:
    """Source evidence must already be prefetched by unprivileged engineering."""
    cache = SOURCE_CACHE
    if cache.is_symlink() or not (cache / ".git").exists():
        deny("INSTALL_REVIEWED_SOURCE_CACHE_UNAVAILABLE")
    manifest = json.loads((REPO / "config/scoped-backport-m365-release.json").read_text())
    for revision in (sha, reviewed_ci_sha, manifest["candidate_sha"],
                     manifest["rollback_sha"], manifest["reviewed_feature_sha"]):
        p = subprocess.run(["git", "-c", f"safe.directory={cache}",
                            "-C", str(cache), "cat-file", "-e",
                            revision + "^{commit}"], capture_output=True,
                           check=False, timeout=20)
        if p.returncode:
            deny("INSTALL_IMMUTABLE_GIT_OBJECT_PREFETCH_REQUIRED")


def required_github_checks(sha: str) -> None:
    """Native root bootstrap must never treat unchecked source as eligible."""
    import urllib.request
    names = frozenset(("repository-hygiene", "documentation",
                       "governed-security-regressions", "runtime-service",
                       "GitGuardian Security Checks"))
    url = ("https://api.github.com/repos/al-teamaot-com/jason/commits/"
           + sha + "/check-runs?per_page=100")
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "jason-exact-release-root-preflight",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read(512_000))
    except (OSError, ValueError, TimeoutError) as exc:
        raise ScopedInstallDenied("SCOPED_BACKPORT_INSTALL_CI_UNAVAILABLE") from exc
    items = data.get("check_runs") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) > 100:
        deny("INSTALL_CI_EVIDENCE_INVALID")
    latest = {}
    for item in items:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and (name not in latest or
                                          item.get("id", 0) > latest[name].get("id", 0)):
                latest[name] = item
    if not names.issubset(latest):
        deny("INSTALL_REQUIRED_CI_CHECK_MISSING")
    if any(latest[name].get("status") != "completed" or
           latest[name].get("conclusion") != "success" for name in names):
        deny("INSTALL_REQUIRED_CI_NOT_GREEN")


def build_public_attestation(private_policy: dict) -> dict:
    """Only non-secret install evidence is readable by the 'al' request client.

    Root's full policy remains private 0600 and is independently attested
    by the installed host worker before any privileged operation.
    """
    allowed = ("trusted_source_sha", "reviewed_ci_sha",
               "root_handler_sha256")
    if (private_policy.get("profile") != "governed-scoped-backport-v1"
            or not all(isinstance(private_policy.get(k), str)
                       for k in allowed)
            or not REGEX_SHA.fullmatch(private_policy["trusted_source_sha"])
            or not REGEX_SHA.fullmatch(private_policy["reviewed_ci_sha"])
            or not REGEX_HASH.fullmatch(private_policy["root_handler_sha256"])
            or any(private_policy.get(k) is not True for k in (
                "native_root_control_supported",
                "automatic_rollback_recovery_installed",
                "exact_signed_owner_approval_required"))):
        deny("INSTALL_PUBLIC_ATTESTATION_POLICY_INVALID")
    return {
        "schema_version": "1.0",
        "profile": "governed-scoped-backport-v1",
        "trusted_source_sha": private_policy["trusted_source_sha"],
        "reviewed_ci_sha": private_policy["reviewed_ci_sha"],
        "root_handler_sha256": private_policy["root_handler_sha256"],
        "native_root_control_supported": True,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
    }


def exact_live() -> dict:
    p = subprocess.run(["docker", "inspect", *ORIGINAL_PROTECTED],
                       capture_output=True, check=False, timeout=20)
    if p.returncode:
        deny("INSTALL_PROTECTED_CONTAINERS_UNAVAILABLE")
    data = json.loads(p.stdout)
    if len(data) != len(ORIGINAL_PROTECTED):
        deny("INSTALL_PROTECTED_CONTAINER_CARDINALITY")
    snapshot = {}
    for d in data:
        if d["Name"].lstrip("/") not in ORIGINAL_PROTECTED or not d["State"]["Running"]:
            deny("INSTALL_PRODUCTION_NOT_RUNNING")
        snapshot[d["Name"].lstrip("/")] = {
            "id": d["Id"], "image": d["Image"],
            "started_at": d["State"]["StartedAt"],
        }
    return snapshot


def preflight(sha: str, reviewed_ci_sha: str) -> dict:
    blobs = source_tree(sha, reviewed_ci_sha)
    expected_absent = (
        INSTALL_ROOT, ROOT_POLICY, ROOT_PUBLIC_ATTEST, ROOT_STATE,
        *(SERVICES / name for name in UNITS),
    )
    if any(p.exists() or p.is_symlink() for p in expected_absent):
        deny("INSTALL_EXISTING_ROOT_CONTROL_REQUIRES_REVIEW")
    if PUBLIC.exists() or PUBLIC.is_symlink():
        deny("INSTALL_PUBLIC_SPOOL_ALREADY_EXISTS")
    freeze = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
    if freeze.is_symlink() or not freeze.is_file():
        deny("INSTALL_PRODUCTION_FREEZE_MISSING")
    freeze_sha = sha256(freeze.read_bytes()).hexdigest()
    manifest = json.loads((REPO / "config/scoped-backport-m365-release.json").read_text())
    if freeze_sha != manifest["freeze_sha256"]:
        deny("INSTALL_PRODUCTION_FREEZE_SHA_CHANGED")
    before = exact_live()
    if (before["jason-runtime"]["image"] != manifest["rollback_runtime_image_id"]
            or before["jason-mcp-pilot"]["image"] != manifest["rollback_mcp_image_id"]):
        deny("INSTALL_PRODUCTION_LKG_CHANGED")
    image_list = json.loads(subprocess.run(
        ["docker", "image", "inspect",
         manifest["runtime_image_id"], manifest["mcp_image_id"],
         manifest["rollback_runtime_image_id"],
         manifest["rollback_mcp_image_id"]],
        capture_output=True, check=True, timeout=20).stdout)
    if len(image_list) != 4:
        deny("INSTALL_IMAGE_CARDINALITY")
    images = {item.get("Id"): item for item in image_list}
    if len(images) != 4:
        deny("INSTALL_IMAGE_DUPLICATED_OR_NOT_DISTINCT")
    for key in ("runtime_image_id", "mcp_image_id",
                "rollback_runtime_image_id", "rollback_mcp_image_id"):
        value = manifest[key]
        metadata = images.get(value)
        expected_revision = (manifest["rollback_sha"]
                             if key.startswith("rollback") else
                             manifest["candidate_sha"])
        if (not metadata or
                (metadata.get("Config") or {}).get("Labels", {}).get(
                    "org.opencontainers.image.revision") != expected_revision):
            deny("INSTALL_CANDIDATE_IMAGE_PROVENANCE_UNVERIFIED")
    result = {
        "schema_version": "1.0",
        "action": "install_scoped_backport_root_control_only",
        "source_sha": sha, "reviewed_ci_sha": reviewed_ci_sha,
        "manifest_candidate_sha": manifest["candidate_sha"],
        "release_id": "release-" + manifest["candidate_sha"][:16],
        "frozen_sha256": freeze_sha,
        "file_sha256": {k: sha256(v).hexdigest() for k, v in sorted(blobs.items())},
        "before": before,
        "production_mutations": False,
        "graph_mutations": False,
        "release_approval_granted": False,
        "source_only": True,
    }
    result["install_scope_sha256"] = sha256(json.dumps(
        {k: v for k, v in result.items() if k != "before"},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def protected_root_controls(evidence: dict) -> None:
    """Exact root protected state readback without touching live services."""
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al":
        deny("INSTALL_AUTHENTICATED_LOCAL_ROOT_REQUIRED")
    state = Path("/var/lib/jason/openclaw/release-manager")
    from datetime import datetime, timezone
    import stat
    control_path = state / "production-control-state.json"
    drift_path = state / "production-drift.json"
    for path in (control_path, drift_path,
                 Path("/var/lib/jason/authority/m365-group-runtime-approle-access-20261112.json")):
        if (path.is_symlink() or not path.is_file()
                or path.stat().st_uid != 0
                or stat.S_IMODE(path.stat().st_mode) != 0o600):
            deny("INSTALL_ROOT_PROTECTED_EVIDENCE_UNTRUSTED")
    control = json.loads(control_path.read_text())
    drift = json.loads(drift_path.read_text())
    receipt = json.loads(Path(
        "/var/lib/jason/authority/m365-group-runtime-approle-access-20261112.json").read_text())
    expected_lkg = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
    observed = datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if (control.get("circuit_breaker", {}).get("state") != "closed"
            or control.get("last_known_good", {}).get("manifest", {}).get("revision") != expected_lkg
            or drift.get("status") != "pass" or drift.get("problems") != []
            or not 0 <= age <= 180):
        deny("INSTALL_PROTECTED_BREAKER_DRIFT_LKG_GATE")
    if (receipt.get("approved_scope") != "aot-m365-group-app-role-runtime-files-four-only"
            or receipt.get("file_count") != 4
            or receipt.get("service_restart") is not False
            or receipt.get("graph_mutation") is not False):
        deny("INSTALL_APPROLE_PREAPPROVAL_RECEIPT_SCOPE")
    for role in ("read","write"):
        parent = Path(f"/opt/jason/bootstrap/secrets/openbao/microsoft-graph-group-{role}-approle")
        if (parent.is_symlink() or not parent.is_dir()
                or parent.stat().st_uid != 0 or parent.stat().st_mode & 0o077):
            deny("INSTALL_APPROLE_DIRECTORY_UNTRUSTED")
        for name in ("role-id","secret-id"):
            p = parent / name
            item = p.lstat()
            if (p.is_symlink() or not stat.S_ISREG(item.st_mode)
                    or item.st_uid != 0 or item.st_gid != 1000
                    or stat.S_IMODE(item.st_mode) != 0o640):
                deny("INSTALL_APPROLE_FILE_ACL_NOT_EXACT")
    if sha256((state / "production-deployment-freeze").read_bytes()).hexdigest() != evidence["frozen_sha256"]:
        deny("INSTALL_EXACT_FREEZE_DIGEST_CHANGED")


def _verify_owner_login() -> str:
    import sys
    from implementation.kernel.signed_owner_release import EXACT_OWNER_OAUTH_SUBJECTS, TID
    info = VERIFIER.lstat()
    if (VERIFIER.is_symlink() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0 or info.st_mode & 0o022
            or sha256(VERIFIER.read_bytes()).hexdigest() != VERIFIER_HASH):
        deny("INSTALL_OWNER_VERIFIER_UNTRUSTED")
    spec = importlib.util.spec_from_file_location("jason_scoped_install_oauth", VERIFIER)
    if spec is None or spec.loader is None:
        deny("INSTALL_ENTRA_OWNER_VERIFIER_UNAVAILABLE")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    if (verifier.TENANT != TID
            or frozenset(verifier.OWNERS) != frozenset(EXACT_OWNER_OAUTH_SUBJECTS)
            or verifier.CLIENT_ID != "9b9996e9-5c34-48b7-948c-f44f89352f89"):
        deny("INSTALL_OWNER_VERIFIER_POLICY_CHANGED")
    root = "https://login.microsoftonline.com/" + TID + "/oauth2/v2.0/"
    challenge = verifier._form(root + "devicecode", {
        "client_id": verifier.CLIENT_ID,
        "scope": verifier.SCOPE,
    })
    if not all(isinstance(challenge.get(k), str)
               for k in ("user_code", "verification_uri", "device_code")):
        deny("INSTALL_OWNER_DEVICE_CODE_UNAVAILABLE")
    expires = min(600, int(challenge.get("expires_in") or 0))
    if expires < 60:
        deny("INSTALL_OWNER_DEVICE_CODE_TOO_SHORT")
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    end = time.monotonic() + expires
    interval = max(5, min(20, int(challenge.get("interval") or 5)))
    while time.monotonic() < end:
        time.sleep(interval)
        result = verifier._form(root + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": verifier.CLIENT_ID,
            "device_code": challenge["device_code"],
        })
        if isinstance(result.get("access_token"), str):
            oid = verifier.jwt_owner(result["access_token"])
            if oid not in EXACT_OWNER_OAUTH_SUBJECTS:
                deny("INSTALL_ENTRA_OWNER_NOT_AUTHORIZED")
            return oid
        if result.get("error") == "slow_down":
            interval = min(20, interval + 5)
        elif result.get("error") != "authorization_pending":
            deny("INSTALL_ENTRA_OWNER_AUTHENTICATION_REJECTED")
    deny("INSTALL_ENTRA_OWNER_AUTHENTICATION_EXPIRED")


def _write_exclusive(path: Path, raw: bytes, *, owner: int = 0,
                     group: int = 0, mode: int = 0o444) -> None:
    if path.exists() or path.is_symlink():
        deny("INSTALL_DESTINATION_ALREADY_EXISTS")
    if path.parent.is_symlink() or not path.parent.is_dir():
        deny("INSTALL_DIRECTORY_UNTRUSTED")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.chown(path, owner, group, follow_symlinks=False)
        os.chmod(path, mode, follow_symlinks=False)
    finally:
        pass


def _root_dir(path: Path, *, uid: int = 0, gid: int = 0,
              mode: int = 0o700) -> None:
    if mode not in (0o700, 0o755):
        deny("INSTALL_DIRECTORY_MODE_UNAPPROVED")
    if path.exists() or path.is_symlink():
        deny("INSTALL_ROOT_DIRECTORY_REPLAY")
    path.mkdir(mode=mode)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def _audit(path: Path, data: dict) -> None:
    raw = json.dumps(data, sort_keys=True, indent=2).encode() + b"\n"
    if path.exists():
        # The first-stage root installer ledger is itself a special root
        # directory; regular installer audit updates must never use a
        # mutable or attacker-selected location.
        p = path.parent
        if p.is_symlink() or p.stat().st_uid != 0:
            deny("INSTALL_AUDIT_DIRECTORY_UNTRUSTED")
        fd, name = tempfile.mkstemp(prefix=".scoped-install-audit-", dir=p)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.chown(name, 0, 0)
            os.chmod(name, 0o600)
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    else:
        _write_exclusive(path, raw, mode=0o600)


def rollback_partial_install(blobs: dict[str, bytes],
                             evidence: dict) -> None:
    """Only remove exact files created in this one installation attempt.

    No global rollback tags, production images, freeze bytes or other root
    services are touched. A foreign file prevents deletion and requires review.
    """
    if os.geteuid() != 0:
        deny("INSTALL_ROLLBACK_REQUIRES_LOCAL_ROOT")
    subprocess.run(["systemctl", "disable", "--now",
                    "jason-scoped-backport-recovery.timer",
                    "jason-scoped-backport-requests.path"],
                   capture_output=True, timeout=30, check=False)
    subprocess.run(["systemctl", "stop",
                    "jason-scoped-backport-recovery.service",
                    "jason-scoped-backport-requests.service"],
                   capture_output=True, timeout=30, check=False)
    if ROOT_PUBLIC_ATTEST.exists() or ROOT_PUBLIC_ATTEST.is_symlink():
        if ROOT_PUBLIC_ATTEST.is_symlink():
            deny("INSTALL_ROLLBACK_PUBLIC_ATTESTATION_LINK")
        pub = json.loads(ROOT_PUBLIC_ATTEST.read_text())
        if (pub.get("trusted_source_sha") != evidence["source_sha"]
                or ROOT_PUBLIC_ATTEST.stat().st_uid != 0
                or pub.get("reviewed_ci_sha") != evidence["reviewed_ci_sha"]):
            deny("INSTALL_ROLLBACK_FOREIGN_PUBLIC_ATTESTATION")
        ROOT_PUBLIC_ATTEST.unlink()
    if ROOT_POLICY.exists() or ROOT_POLICY.is_symlink():
        if ROOT_POLICY.is_symlink():
            deny("INSTALL_ROLLBACK_ROOT_POLICY_LINK")
        doc = json.loads(ROOT_POLICY.read_text())
        if (doc.get("profile") != "governed-scoped-backport-v1"
                or doc.get("trusted_source_sha") != evidence["source_sha"]
                or ROOT_POLICY.stat().st_uid != 0):
            deny("INSTALL_ROLLBACK_FOREIGN_ROOT_POLICY")
        ROOT_POLICY.unlink()
    for name in UNITS:
        dest = SERVICES / name
        if dest.exists() or dest.is_symlink():
            source_key = (UNIT_DIR / name).as_posix()
            if (dest.is_symlink() or dest.stat().st_uid != 0
                    or dest.read_bytes() != blobs[source_key]):
                deny("INSTALL_ROLLBACK_UNIT_BYTES_DRIFT")
            dest.unlink()
    for name in reversed(FILES):
        dest = INSTALL_ROOT / name
        if dest.exists() or dest.is_symlink():
            if (dest.is_symlink() or dest.stat().st_uid != 0
                    or dest.read_bytes() != blobs[name]):
                deny("INSTALL_ROLLBACK_ROOT_SOURCE_DRIFT")
            dest.unlink()
    for root in (PUBLIC, ROOT_STATE):
        if root.exists() or root.is_symlink():
            if root.is_symlink():
                deny("INSTALL_ROLLBACK_STATE_SYMLINK")
            children = PUBLIC_DIRS if root == PUBLIC else ROOT_DIRS
            for name in reversed(children):
                p = root / name
                if p.exists():
                    if any(p.iterdir()):
                        deny("INSTALL_ROLLBACK_NONEMPTY_NEW_STATE")
                    p.rmdir()
            if any(root.iterdir()):
                deny("INSTALL_ROLLBACK_UNREVIEWED_STATE")
            root.rmdir()
    for p in (
        INSTALL_ROOT / "implementation/kernel",
        INSTALL_ROOT / "implementation",
        INSTALL_ROOT / "tools",
        INSTALL_ROOT,
    ):
        if p.exists() or p.is_symlink():
            if p.is_symlink() or any(p.iterdir()):
                deny("INSTALL_ROLLBACK_UNREVIEWED_ROOT_DIR")
            p.rmdir()
    subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=30)
    if exact_live() != evidence["before"]:
        deny("INSTALL_ROLLBACK_PROTECTED_SERVICES_CHANGED")
    freeze = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
    if sha256(freeze.read_bytes()).hexdigest() != evidence["frozen_sha256"]:
        deny("INSTALL_ROLLBACK_FREEZE_CHANGED")


def install(sha: str, reviewed_ci_sha: str, evidence: dict,
            *, exact_scope: str) -> dict:
    if (os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al"
            or exact_scope != evidence["install_scope_sha256"]):
        deny("INSTALL_AUTHENTICATED_EXACT_OWNER_SCOPE_REQUIRED")
    # Re-run preflight as privileged operator, then independently verify
    # fresh Entra OAuth Owner before any privileged root file is written.
    current = preflight(sha, reviewed_ci_sha)
    protected_root_controls(evidence)
    if current != evidence:
        deny("INSTALL_PREFLIGHT_CHANGED")
    print("ACTION=INSTALL_SCOPED_BACKPORT_RELEASE_CONTROL_ONLY", flush=True)
    print("SOURCE_SHA=" + sha, flush=True)
    print("REVIEWED_CI_SHA=" + reviewed_ci_sha, flush=True)
    print("INSTALL_SCOPE_SHA256=" + exact_scope, flush=True)
    print("FREEZE_SHA256=" + evidence["frozen_sha256"], flush=True)
    print("RUNTIME_MCP_REPLACEMENT_APPROVED=false", flush=True)
    print("GRAPH_PROVIDER_MUTATION_APPROVED=false", flush=True)
    oid = _verify_owner_login()
    if input("Type " + ACTION + " to approve only this root installer: ").strip() != ACTION:
        deny("INSTALL_EXACT_OWNER_DECISION_NOT_CONFIRMED")
    if preflight(sha, reviewed_ci_sha) != evidence:
        deny("INSTALL_PREFLIGHT_DRIFT_BEFORE_FIRST_WRITE")
    protected_root_controls(evidence)
    # Root installer is itself source-bound to this exact immutable SHA.
    blob = git("show", sha + ":tools/scoped_backport_root_install.py")
    if blob != Path(__file__).read_bytes():
        deny("INSTALLER_SOURCE_BYTES_CHANGED")
    if LEDGER.exists():
        if (LEDGER.is_symlink() or not LEDGER.is_dir()
                or LEDGER.stat().st_uid != 0
                or stat.S_IMODE(LEDGER.stat().st_mode) != 0o700):
            deny("INSTALL_LEDGER_UNTRUSTED")
    else:
        _root_dir(LEDGER)
    journal = LEDGER / (sha + ".json")
    if journal.exists() or journal.is_symlink():
        deny("INSTALL_EXACT_ROOT_APPROVAL_REPLAY")
    _audit(journal, {
        "schema_version": "1.0", "source_sha": sha,
        "reviewed_ci_sha": reviewed_ci_sha,
        "install_scope_sha256": exact_scope,
        "freeze_sha256": evidence["frozen_sha256"],
        "owner_oid": oid, "owner_tenant":
        "f7054323-d52b-4863-8c2f-1898f0b6077c",
        "owner_assurance": "fresh_verified_entra_device_code_signed_jwt",
        "authorization": "single_exact_root_control_install",
        "standing_permission": False, "status": "intent_durable_no_mutation",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    blobs = source_tree(sha, reviewed_ci_sha)
    try:
        _root_dir(INSTALL_ROOT, mode=0o755)
        _root_dir(INSTALL_ROOT / "tools", mode=0o755)
        _root_dir(INSTALL_ROOT / "implementation", mode=0o755)
        _root_dir(INSTALL_ROOT / "implementation/kernel", mode=0o755)
        for name in FILES:
            dest = INSTALL_ROOT / name
            _write_exclusive(dest, blobs[name])
        for name in UNITS:
            dest = SERVICES / name
            _write_exclusive(dest, blobs[(UNIT_DIR / name).as_posix()])
        _root_dir(ROOT_STATE)
        for name in ROOT_DIRS:
            _root_dir(ROOT_STATE / name)
        al = pwd.getpwnam("al")
        _root_dir(PUBLIC, uid=al.pw_uid, gid=al.pw_gid)
        for name in PUBLIC_DIRS:
            _root_dir(PUBLIC / name, uid=al.pw_uid, gid=al.pw_gid)
        policy = {
            "schema_version": "1.0", "profile": "governed-scoped-backport-v1",
            "trusted_source_sha": sha,
            "reviewed_ci_sha": reviewed_ci_sha,
            "native_root_control_supported": True,
            "automatic_rollback_recovery_installed": True,
            "exact_signed_owner_approval_required": True,
            "no_global_owner_elevation": True,
        }
        fields = {
            "root_handler_sha256": "tools/scoped_backport_native_root.py",
            "native_host_sha256": "tools/scoped_backport_native_host.py",
            "core_sha256": "tools/scoped_backport_release.py",
            "request_module_sha256": "tools/scoped_backport_release_request.py",
            "owner_local_sha256": "tools/scoped_backport_owner_local_approval.py",
            "kernel_owner_proof_sha256": "implementation/kernel/signed_owner_release.py",
            "native_deploy_sha256": "tools/deploy_live_container.py",
            "native_mcp_projection_sha256": "tools/pmv4_mcp_projection.py",
            "root_recovery_sha256": "tools/scoped_backport_native_recovery.py",
            "recovery_unit_sha256": (UNIT_DIR / "jason-scoped-backport-recovery.service").as_posix(),
            "recovery_timer_sha256": (UNIT_DIR / "jason-scoped-backport-recovery.timer").as_posix(),
            "request_unit_sha256": (UNIT_DIR / "jason-scoped-backport-requests.service").as_posix(),
            "request_path_sha256": (UNIT_DIR / "jason-scoped-backport-requests.path").as_posix(),
        }
        policy.update({k: sha256(blobs[v]).hexdigest() for k, v in fields.items()})
        _write_exclusive(ROOT_POLICY,
                         json.dumps(policy, sort_keys=True, indent=2).encode()+b"\n",
                         mode=0o600)
        public_attestation = build_public_attestation(policy)
        _write_exclusive(ROOT_PUBLIC_ATTEST,
                         json.dumps(public_attestation, sort_keys=True, indent=2).encode()+b"\n",
                         mode=0o644)
        subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=30)
        subprocess.run(["systemctl", "enable", "--now",
                        "jason-scoped-backport-recovery.timer",
                        "jason-scoped-backport-requests.path"], check=True, timeout=45)
        from tools.scoped_backport_native_host import NativeScopedBackportHost
        # The installed worker must independently verify its root-owned bytes.
        # Do not run the mutable source as the actual root worker.
        probe = subprocess.run([
            "/usr/bin/python3", "-I",
            "/usr/local/lib/jason/scoped-backport/tools/scoped_backport_native_root.py",
            "--drain",
        ], capture_output=True, text=True, timeout=30, check=False)
        if probe.returncode != 0:
            deny("INSTALL_ROOT_WORKER_TRUST_READBACK_FAILED")
        if exact_live() != evidence["before"]:
            deny("INSTALL_PROTECTED_CONTAINERS_CHANGED")
        if sha256(Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze").read_bytes()).hexdigest() != evidence["frozen_sha256"]:
            deny("INSTALL_FREEZE_CHANGED")
        _audit(journal, {
            "schema_version": "1.0", "source_sha": sha,
            "install_scope_sha256": exact_scope,
            "freeze_sha256": evidence["frozen_sha256"],
            "owner_oid": oid, "status": "installed_attested_root_control_only",
            "production_runtime_changed": False,
            "provider_writes": False,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
    except BaseException as exc:
        try:
            rollback_partial_install(blobs, evidence)
            _audit(journal, {
                "schema_version": "1.0", "source_sha": sha,
                "install_scope_sha256": exact_scope,
                "status": "exact_installer_failure_rolled_back",
                "failure_class": type(exc).__name__,
                "production_mutations": False, "provider_writes": False,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
        except BaseException as recovery:
            _audit(journal, {
                "schema_version": "1.0", "source_sha": sha,
                "install_scope_sha256": exact_scope,
                "status": "partial_install_requires_owner_review",
                "failure_class": type(exc).__name__,
                "rollback_failure_class": type(recovery).__name__,
                "production_mutations": False, "provider_writes": False,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
            raise ScopedInstallDenied(
                "SCOPED_BACKPORT_ROOT_INSTALL_ROLLBACK_UNVERIFIED") from recovery
        raise

    return {
        "status": "installed_attested_root_control_only",
        "source_sha": sha, "install_scope_sha256": exact_scope,
        "runtime_mcp_changed": False, "provider_writes": False,
        "release_approved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--reviewed-ci-sha", required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--exact-install-scope-sha256", default="")
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("exactly one of --check or --apply required")
    evidence = preflight(args.source_sha, args.reviewed_ci_sha)
    if args.check:
        print(json.dumps(evidence, sort_keys=True, indent=2))
        return 0
    result = install(args.source_sha, args.reviewed_ci_sha, evidence,
                     exact_scope=args.exact_install_scope_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
