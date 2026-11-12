#!/usr/bin/env python3
"""Root-gated one-transaction provider OAuth credential projection.

This restores no secrets and creates no API tokens. The only production
mutation allowed is replacing the *same* verified MCP image with precisely two
new read-only Constant Contact AppRole binds and three non-secret path variables.
It reuses Jason's existing native container replacer and requires fresh Entra
Owner authentication before touching a container.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import pwd
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

OPERATION = "constant-contact-oauth-mcp-approle-bind-v1"
SCRIPT_INSTALLED = Path("/usr/local/lib/jason/governed_provider_oauth_projection.py")
POLICY = Path("/etc/jason-owner-release/constant-contact-oauth-mcp-projection.json")
TRUSTED_AUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
DEPLOYER = Path("/usr/local/lib/jason/deploy_live_container_owner_signer_2450.py")
LEDGER_DIR = Path("/etc/jason-owner-release/constant-contact-oauth-mcp-ledger")
LIVE = "jason-mcp-pilot"
ROLLBACK = "jason-mcp-rollback-constant-contact-oauth-20261112"
RUNTIME = "jason-runtime"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
RUNTIME_IMAGE = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
SIGNER_DEST = "/run/jason-secrets/owner-release/private_key"
SIGNER_HOST = "/var/lib/jason/runtime-secrets/owner-release/private_key"
ROLE_SOURCE = "/var/lib/jason/runtime-secrets/openbao/constant-contact-oauth-client-approle/role-id"
SECRET_SOURCE = "/var/lib/jason/runtime-secrets/openbao/constant-contact-oauth-client-approle/secret-id"
ROLE_DEST = "/run/jason-secrets/openbao/constant-contact/role_id"
SECRET_DEST = "/run/jason-secrets/openbao/constant-contact/secret_id"
OAUTH_DB = "/var/lib/jason/openclaw/constant-contact/oauth.sqlite3"
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
TRANSACTION_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
HOST_RELEASE = Path("/opt/jason/current")
HEALTH_URL = "http://127.0.0.1:8000/healthz"

class ProjectionDenied(PermissionError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def root_file(path: Path, maximum: int = 131072, mutable_parent: bool = False) -> bytes:
    parent = path.parent.lstat()
    if (path.parent.is_symlink() or (not mutable_parent and
            (parent.st_uid != 0 or parent.st_mode & 0o022))):
        raise ProjectionDenied("UNSAFE_ROOT_PARENT:" + str(path.parent))
    if path.is_symlink():
        raise ProjectionDenied("ROOT_SYMLINK_DENIED")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ProjectionDenied("ROOT_OPEN_DENIED") from exc
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022
                or s.st_size > maximum):
            raise ProjectionDenied("ROOT_FILE_NOT_TRUSTED:" + str(path))
        data = os.read(fd, maximum + 1)
        if len(data) != s.st_size:
            raise ProjectionDenied("ROOT_FILE_SIZE_UNSTABLE")
        return data
    finally:
        os.close(fd)


def docker(name: str) -> dict:
    proc = subprocess.run(["docker", "inspect", name], capture_output=True,
                          text=True, timeout=15, check=True)
    rows = json.loads(proc.stdout)
    if not isinstance(rows, list) or len(rows) != 1:
        raise ProjectionDenied("DOCKER_INSPECT_CARDINALITY")
    return rows[0]


def env_map(obj: dict) -> dict[str, str]:
    out = {}
    for entry in obj.get("Config", {}).get("Env") or []:
        if "=" in entry:
            k, v = entry.split("=", 1)
            out[k] = v
    return out


def mounts(obj: dict) -> list[tuple[str, str, str, bool]]:
    return sorted(
        (str(m.get("Type")), str(m.get("Source")),
         str(m.get("Destination")), bool(m.get("RW")))
        for m in obj.get("Mounts", []) or []
    )


def runtime_identity() -> pwd.struct_passwd:
    return pwd.getpwnam("al")


def credential_file(path: str, owner: pwd.struct_passwd) -> None:
    p = Path(path)
    info = p.lstat()
    parent = p.parent.lstat()
    if (p.is_symlink() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0 or info.st_gid != owner.pw_gid
            or stat.S_IMODE(info.st_mode) != 0o640
            or info.st_size < 20 or info.st_size > 512
            or p.parent.is_symlink() or parent.st_uid != 0
            or parent.st_gid != owner.pw_gid
            or stat.S_IMODE(parent.st_mode) != 0o750):
        raise ProjectionDenied("OPENBAO_APPROLE_FILE_POLICY_DENIED")
    # No file content is read, written or printed by the projection.


def verify_rollback_budget() -> None:
    # The protected LKG desired-state permits at most 20 stopped rollback
    # containers. Do not add a 21st: that would reopen the root drift breaker.
    response = subprocess.check_output(
        ["docker", "ps", "-a", "--filter", "status=exited",
         "--format", "{{.Names}}"],
        text=True, timeout=15,
    )
    prefixes = (
        "jason-runtime-rollback-", "jason-mcp-pilot-rollback-",
        "jason-mcp-rollback-", "jason-teams-gateway-rollback-",
    )
    count = sum(any(line.strip().startswith(p) for p in prefixes)
                for line in response.splitlines())
    if count >= 20:
        raise ProjectionDenied("ROOT_ROLLBACK_CONTAINER_RETENTION_BUDGET_FULL")


def clean_production() -> dict:
    # The legacy spool directory is writable by al. Require actual root-owned,
    # no-follow file descriptors, rather than trusting its path or readback copy.
    control = json.loads(root_file(CONTROL, mutable_parent=True))
    drift = json.loads(root_file(DRIFT, mutable_parent=True))
    manifest = (control.get("last_known_good") or {}).get("manifest") or {}
    if (control.get("circuit_breaker", {}).get("state") != "closed" or
            manifest.get("complete") is not True):
        raise ProjectionDenied("PRODUCTION_BREAKER_OR_LKG_UNVERIFIED")
    for field, expected in (
        ("revision", LKG), ("runtime_revision", LKG), ("mcp_revision", LKG),
        ("host_revision", LKG), ("runtime_image_id", RUNTIME_IMAGE),
        ("mcp_image_id", MCP_IMAGE),
    ):
        if manifest.get(field) != expected:
            raise ProjectionDenied("PRODUCTION_LKG_REVISION_MISMATCH:" + field)
    when = datetime.fromisoformat(str(drift.get("observed_at", "")).replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - when).total_seconds()
    if (when.tzinfo is None or drift.get("status") != "pass" or
            drift.get("problems") != [] or age < -10 or age > 180):
        raise ProjectionDenied("ROOT_DRIFT_NOT_FRESH_CLEAN")
    if sha(FREEZE.read_bytes()) != FREEZE_SHA:
        raise ProjectionDenied("ORIGINAL_PRODUCTION_FREEZE_CHANGED")
    if HOST_RELEASE.resolve(strict=True) != Path("/opt/jason/releases") / LKG:
        raise ProjectionDenied("LIVE_HOST_RELEASE_MISMATCH")
    runtime, mcp = docker(RUNTIME), docker(LIVE)
    if (runtime.get("Image") != RUNTIME_IMAGE or mcp.get("Image") != MCP_IMAGE
            or runtime.get("State", {}).get("Health", {}).get("Status") != "healthy"
            or mcp.get("State", {}).get("Status") != "running"):
        raise ProjectionDenied("LIVE_CONTAINER_IMAGE_OR_HEALTH_MISMATCH")
    for obj in (runtime, mcp):
        if obj.get("Config", {}).get("Labels", {}).get(
                "com.teamaot.jason.source_revision") != LKG:
            raise ProjectionDenied("LIVE_CONTAINER_REVISION_MISMATCH")
    if (mcp.get("HostConfig", {}).get("ReadonlyRootfs") is not True or
            mcp.get("HostConfig", {}).get("Privileged") is True or
            "ALL" not in (mcp.get("HostConfig", {}).get("CapDrop") or [])):
        raise ProjectionDenied("MCP_SANDBOX_POLICY_NOT_ENFORCED")
    oldmounts = mounts(mcp)
    if ("bind", SIGNER_HOST, SIGNER_DEST, False) not in oldmounts:
        raise ProjectionDenied("EXISTING_OWNER_SIGNER_BIND_MISSING")
    if any(item[2] in (ROLE_DEST, SECRET_DEST) for item in oldmounts):
        raise ProjectionDenied("PROVIDER_BIND_ALREADY_PRESENT")
    if any(item[2] in (ROLE_DEST, SECRET_DEST) for item in mounts(runtime)):
        raise ProjectionDenied("PROVIDER_MOUNT_ON_RUNTIME_UNEXPECTED")
    oldenv = env_map(mcp)
    for key in (
        "JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH",
        "JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH",
        "JASON_CONSTANT_CONTACT_OAUTH_DB",
    ):
        if key in oldenv:
            raise ProjectionDenied("PROVIDER_CONFIG_ALREADY_PRESENT")
    if oldenv.get("JASON_OWNER_RELEASE_ED25519_KEY_PATH") != SIGNER_DEST:
        raise ProjectionDenied("OWNER_SIGNER_CONFIGURATION_MISSING")
    if oldenv.get("JASON_PMV4_STAGE_A0_ISSUER_ENABLED") != "false":
        raise ProjectionDenied("UNRELATED_PMV4_AUTHORITY_ACTIVE")
    owner = runtime_identity()
    credential_file(ROLE_SOURCE, owner)
    credential_file(SECRET_SOURCE, owner)
    return {
        "mcp_id": mcp["Id"], "runtime_id": runtime["Id"],
        "mcp_image": mcp["Image"], "mounts": oldmounts,
        "env": oldenv, "networks": sorted((mcp.get("NetworkSettings", {}).get("Networks") or {}).keys()),
        "user": mcp.get("Config", {}).get("User"),
    }


def validate_post(pre: dict) -> dict:
    mcp = docker(LIVE)
    if (mcp["Id"] == pre["mcp_id"] or mcp["Image"] != MCP_IMAGE
            or mcp.get("State", {}).get("Status") != "running"
            or mcp.get("Config", {}).get("User") != pre["user"]):
        raise ProjectionDenied("MCP_REPLACEMENT_IDENTITY_UNVERIFIED")
    newmounts = sorted(pre["mounts"] + [
        ("bind", ROLE_SOURCE, ROLE_DEST, False),
        ("bind", SECRET_SOURCE, SECRET_DEST, False),
    ])
    if mounts(mcp) != newmounts:
        raise ProjectionDenied("UNEXPECTED_EXTRA_OR_WRITABLE_MOUNTS")
    newenv = dict(pre["env"])
    newenv.update({
        "JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH": ROLE_DEST,
        "JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH": SECRET_DEST,
        "JASON_CONSTANT_CONTACT_OAUTH_DB": OAUTH_DB,
    })
    if env_map(mcp) != newenv:
        raise ProjectionDenied("UNRELATED_ENVIRONMENT_CHANGE")
    if sorted((mcp.get("NetworkSettings", {}).get("Networks") or {}).keys()) != pre["networks"]:
        raise ProjectionDenied("NETWORK_POLICY_CHANGED")
    if (mcp.get("HostConfig", {}).get("ReadonlyRootfs") is not True or
            mcp.get("HostConfig", {}).get("Privileged") is True or
            "ALL" not in (mcp.get("HostConfig", {}).get("CapDrop") or [])):
        raise ProjectionDenied("MCP_SANDBOX_HARDENING_LOST")
    if docker(RUNTIME)["Id"] != pre["runtime_id"]:
        raise ProjectionDenied("TICKET_RUNTIME_CHANGED")
    if sha(FREEZE.read_bytes()) != FREEZE_SHA:
        raise ProjectionDenied("PRODUCTION_FREEZE_CHANGED")
    if HOST_RELEASE.resolve(strict=True) != Path("/opt/jason/releases") / LKG:
        raise ProjectionDenied("HOST_RELEASE_CHANGED")
    # Read only a yes/no file presence assertion inside the MCP container.
    probe = ("from pathlib import Path; import os;"
             "assert all(Path(os.environ[k]).is_file() for k in "
             "('JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH',"
             "'JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH'));"
             "print('MCP_CC_APPROLE_FILES_PRESENT=true')")
    subprocess.run(["docker", "exec", LIVE, "python", "-c", probe],
                   check=True, timeout=20, stdout=subprocess.DEVNULL)
    # Verify controls again without demanding a synchronous watchdog run.
    ctrl = json.loads(root_file(CONTROL, mutable_parent=True))
    if (ctrl.get("circuit_breaker", {}).get("state") != "closed" or
            ctrl.get("last_known_good", {}).get("manifest", {}).get("revision") != LKG):
        raise ProjectionDenied("ROOT_PRODUCTION_POLICY_CHANGED")
    return {"verified": True, "new_mcp_id": mcp["Id"]}


def fresh_owner_approval(helper) -> str:
    # The root-owned existing helper independently validates Azure JWT
    # issuer/audience/JWKS, exact tenant, Owner OID and Jason.Read scope.
    root = "https://login.microsoftonline.com/" + helper.TENANT + "/oauth2/v2.0/"
    challenge = helper._form(root + "devicecode", {
        "client_id": helper.CLIENT_ID, "scope": helper.SCOPE,
    })
    if not all(isinstance(challenge.get(k), str)
               for k in ("device_code", "user_code", "verification_uri")):
        raise ProjectionDenied("ENTRA_DEVICE_CHALLENGE_UNAVAILABLE")
    deadline = time.monotonic() + min(int(challenge.get("expires_in", 0)), 600)
    if deadline - time.monotonic() < 59:
        raise ProjectionDenied("ENTRA_DEVICE_CODE_LIFETIME_TOO_SHORT")
    print("EXACT_ACTION=" + OPERATION, flush=True)
    print("MCP_IMAGE_ID=" + MCP_IMAGE, flush=True)
    print("READONLY_APPROLE_BINDS=2", flush=True)
    print("UNRELATED_RUNTIME_OR_PMV4_CHANGES=false", flush=True)
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    interval = max(5, min(20, int(challenge.get("interval", 5))))
    while time.monotonic() < deadline:
        time.sleep(interval)
        result = helper._form(root + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": helper.CLIENT_ID,
            "device_code": challenge["device_code"],
        })
        if isinstance(result.get("access_token"), str):
            return helper.jwt_owner(result["access_token"])
        code = result.get("error")
        if code == "authorization_pending":
            continue
        if code == "slow_down":
            interval = min(20, interval + 5)
            continue
        raise ProjectionDenied("ENTRA_OWNER_AUTHORIZATION_DENIED:" + str(code)[:70])
    raise ProjectionDenied("ENTRA_OWNER_AUTHORIZATION_EXPIRED")


def atomic_record(path: Path, record: dict) -> None:
    data = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchown(fd, 0, 0)
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def production_gate():
    # Serialize with the installed Release Manager and drift watchdog. Do not
    # hold the lock for the interactive Owner login; acquire it only for the
    # final authoritative reread, one-shot claim, mutation and verification.
    fd = os.open(TRANSACTION_LOCK, os.O_RDWR | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_mode & 0o002:
            raise ProjectionDenied("NATIVE_TRANSACTION_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProjectionDenied("ANOTHER_PRODUCTION_TRANSACTION_ACTIVE") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def execute() -> None:
    if os.geteuid() != 0 or sys.flags.isolated != 1:
        raise ProjectionDenied("ROOT_ISOLATED_PYTHON_REQUIRED")
    if Path(__file__).resolve(strict=True) != SCRIPT_INSTALLED:
        raise ProjectionDenied("MUST_EXECUTE_INSTALLED_ROOT_MODULE")
    source = root_file(SCRIPT_INSTALLED)
    doc = json.loads(root_file(POLICY))
    expected = {
        "schema_version": "1.0", "operation": OPERATION, "one_shot": True,
        "lkg_sha": LKG, "mcp_image": MCP_IMAGE, "runtime_image": RUNTIME_IMAGE,
        "freeze_sha256": FREEZE_SHA,
        "role_source": ROLE_SOURCE, "secret_source": SECRET_SOURCE,
        "role_destination": ROLE_DEST, "secret_destination": SECRET_DEST,
        "oauth_db": OAUTH_DB,
        "script_sha256": doc.get("script_sha256"),
        "trusted_auth_helper_sha256": doc.get("trusted_auth_helper_sha256"),
        "native_deployer_sha256": doc.get("native_deployer_sha256"),
        "owner_authentication": "fresh_entra_device_code_exact_owner",
        "unrelated_profiles": "preserve_existing_disabled",
    }
    if doc != expected:
        raise ProjectionDenied("ROOT_POLICY_MISMATCH")
    for path, key in (
        (SCRIPT_INSTALLED, "script_sha256"),
        (TRUSTED_AUTH, "trusted_auth_helper_sha256"),
        (DEPLOYER, "native_deployer_sha256"),
    ):
        if len(str(doc[key])) != 64 or sha(root_file(path)) != doc[key]:
            raise ProjectionDenied("REVIEWED_EXECUTABLE_HASH_MISMATCH")
    ledger_info = LEDGER_DIR.lstat()
    if (LEDGER_DIR.is_symlink() or ledger_info.st_uid != 0 or
            stat.S_IMODE(ledger_info.st_mode) != 0o700):
        raise ProjectionDenied("ROOT_LEDGER_NOT_TRUSTED")
    if list(LEDGER_DIR.glob(OPERATION + "*")):
        raise ProjectionDenied("ONE_SHOT_ALREADY_CLAIMED")
    spec = importlib.util.spec_from_file_location(
        "root_trusted_owner_auth", str(TRUSTED_AUTH)
    )
    if spec is None or spec.loader is None:
        raise ProjectionDenied("ROOT_AUTH_HELPER_UNAVAILABLE")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.trusted_signer()
    pre = clean_production()
    verify_rollback_budget()
    oid = fresh_owner_approval(helper)
    helper.trusted_signer()
    with production_gate():
        updated = clean_production()
        verify_rollback_budget()
        if updated["mcp_id"] != pre["mcp_id"] or updated["runtime_id"] != pre["runtime_id"]:
            raise ProjectionDenied("PRODUCTION_CHANGED_DURING_OWNER_AUTH")
        attempt = LEDGER_DIR / (OPERATION + ".attempt.json")
        atomic_record(attempt, {
            "schema_version": "1.0", "operation": OPERATION,
            "when_utc": datetime.now(timezone.utc).isoformat(),
            "owner_oid": oid,
            "mcp_image": MCP_IMAGE, "old_mcp_id": pre["mcp_id"],
            "freeze_sha256": FREEZE_SHA,
            "approved_source_sha256": doc["script_sha256"],
            "one_action": True, "standing_authority": False,
            "state": "claimed_before_mutation",
        })
        cmd = [
            sys.executable, str(DEPLOYER),
            "--live", LIVE, "--image", MCP_IMAGE, "--rollback", ROLLBACK,
            "--source-revision", LKG, "--health-url", HEALTH_URL,
            "--health-attempts", "12", "--health-interval", "2",
            "--harden",
            "--set-env", "JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH=" + ROLE_DEST,
            "--set-env", "JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH=" + SECRET_DEST,
            "--set-env", "JASON_CONSTANT_CONTACT_OAUTH_DB=" + OAUTH_DB,
            "--add-readonly-bind", ROLE_SOURCE + ":" + ROLE_DEST,
            "--add-readonly-bind", SECRET_SOURCE + ":" + SECRET_DEST,
        ]
        receipt = {"schema_version": "1.0", "operation": OPERATION, "outcome": "failed"}
        try:
            subprocess.run(cmd, check=True, timeout=200, stdout=subprocess.DEVNULL)
            details = validate_post(pre)
            receipt.update({"outcome": "verified", **details})
        except Exception:
            # The native deployer performs its own fail-safe rollback during a
            # failed replacement. Restore its stopped prior container if a later
            # postflight check rejects the otherwise healthy replacement.
            try:
                if subprocess.run(["docker", "inspect", ROLLBACK],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL).returncode == 0:
                    subprocess.run(["docker", "rm", "-f", LIVE], check=True,
                                   timeout=45, stdout=subprocess.DEVNULL)
                    subprocess.run(["docker", "rename", ROLLBACK, LIVE], check=True,
                                   timeout=30, stdout=subprocess.DEVNULL)
                    subprocess.run(["docker", "start", LIVE], check=True,
                                   timeout=45, stdout=subprocess.DEVNULL)
                receipt["rollback_to_old_container"] = docker(LIVE)["Id"] == pre["mcp_id"]
            except Exception:
                receipt["rollback_to_old_container"] = False
            raise
        finally:
            receipt["when_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_record(LEDGER_DIR / (OPERATION + ".result.json"), receipt)
    print("CONSTANT_CONTACT_OAUTH_MCP_PROJECTION=VERIFIED")
    print("TWO_READONLY_APPROLE_BINDS=VERIFIED")
    print("TICKET_RUNTIME_UNCHANGED=true")
    print("PRODUCTION_FREEZE_UNCHANGED=true")
    print("OWNER_AUTH=verified_entra_oauth")
    print("ONE_SHOT_AUDIT=" + str(attempt))


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.check_only:
            # Never claim root-mutating preflight in a non-root context.
            c = json.loads(Path(
                "/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json"
            ).read_bytes())
            if (c.get("circuit_breaker", {}).get("state") != "closed" or
                    c.get("last_known_good", {}).get("manifest", {}).get("revision") != LKG):
                raise ProjectionDenied("READ_ONLY_LKG_NOT_VERIFIED")
            before = docker(LIVE)
            if before.get("Image") != MCP_IMAGE:
                raise ProjectionDenied("READ_ONLY_MCP_IMAGE_MISMATCH")
            if any(m[2] in (ROLE_DEST, SECRET_DEST) for m in mounts(before)):
                raise ProjectionDenied("READ_ONLY_ALREADY_ACTIVE")
            print("READ_ONLY_CC_MCP_PROJECTION_PREFLIGHT=PASS")
            print("PROJECTION_EXECUTED=false")
        else:
            execute()
    except Exception as exc:
        print("CONSTANT_CONTACT_OAUTH_MCP_PROJECTION=DENIED " +
              type(exc).__name__ + ":" + str(exc)[:145], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
