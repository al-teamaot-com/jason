#!/usr/bin/env python3
"""Owner-operated exact-image, one-variable MCP configuration maintenance.

Not a release or image promotion. Review is read-only. Apply must be initiated
by the individual Owner in a local authenticated sudo TTY, never by automation.
The active production freeze remains byte-identical throughout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import pwd
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any

ROOT = pathlib.Path("/var/lib/jason/openclaw/release-manager")
FREEZE = ROOT / "production-deployment-freeze"
LOCK = ROOT / "production-transaction.lock"
AUDIT = ROOT / "root-operator-approvals"
REPO = pathlib.Path("/opt/jason/current")
DEPLOY = REPO / "tools/deploy_live_container.py"
LIVE = "jason-mcp-pilot"
ROLLBACK = "jason-mcp-pilot-rollback-owner-allowlist-20261117"
VERSION = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
DEPLOY_SHA256 = "afc8eccea53e01a516e369f2a4efecbb28efb3fffc9dc4b3d48d2e0d9dcc01a4"
FREEZE_SHA256 = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
KEY = "JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES"
OLD = "person-al"
NEW = "person-al,person-entra-bee80bdcffb04c50b453c09d4d411f5f"
ACCOUNT = "al@teamaot.com"
OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
TID = "f7054323-d52b-4863-8c2f-1898f0b6077c"
ORIGIN = "/var/lib/jason/openclaw/teams-identity-bindings.sqlite3"
SCOPE = {
    "operation": "owner_authenticated_exact_image_mcp_configuration_maintenance",
    "source_revision": VERSION, "image_digest": IMAGE,
    "container": LIVE, "changed_environment_key": KEY,
    "original_value": OLD, "new_value": NEW, "other_configuration_changed": False,
    "new_code_or_image": False, "freeze_restored_byte_exact": True,
    "rollback": "restore_exact_original_docker_container",
    "freeze_sha256": FREEZE_SHA256,
}
DIGEST = hashlib.sha256(json.dumps(SCOPE, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fail(reason: str) -> None:
    raise RuntimeError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def cmd(*args: str, timeout: int = 45, check: bool = True) -> str:
    cp = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    if check and cp.returncode:
        fail("COMMAND_FAILED:" + args[0] + ":" + str(cp.returncode) + ":" + (cp.stderr or "")[:160])
    return cp.stdout.strip()


def docker(name: str) -> dict[str, Any]:
    found = json.loads(cmd("docker", "inspect", name, timeout=20))
    if len(found) != 1:
        fail("DOCKER_INSPECT_NOT_UNIQUE")
    return found[0]


def environment(obj: dict[str, Any]) -> dict[str, str]:
    values = obj.get("Config", {}).get("Env", []) or []
    if any(not isinstance(x, str) or "=" not in x for x in values):
        fail("MALFORMED_ENVIRONMENT")
    if len(set(v.split("=", 1)[0] for v in values)) != len(values):
        fail("DUPLICATE_ENVIRONMENT_KEY")
    return dict(v.split("=", 1) for v in values)


def freeze() -> None:
    st = FREEZE.lstat()
    owner = pwd.getpwnam("al").pw_uid
    if (FREEZE.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_uid != owner
            or stat.S_IMODE(st.st_mode) != 0o600
            or sha(FREEZE.read_bytes()) != FREEZE_SHA256):
        fail("PRODUCTION_FREEZE_DRIFT")
    val = json.loads(FREEZE.read_text())
    if val.get("status") != "active" or val.get("scope") != "manual-and-automatic-production-promotions":
        fail("FREEZE_STATE_UNEXPECTED")


def account() -> None:
    c = sqlite3.connect("file:" + ORIGIN + "?mode=ro", uri=True, timeout=5)
    try:
        rows = c.execute(
            "SELECT email_address,jason_identity_id,microsoft_tenant_id,microsoft_object_id,status "
            "FROM microsoft_identity_bindings WHERE lower(email_address)=?", (ACCOUNT,)
        ).fetchall()
    finally:
        c.close()
    if rows != [(ACCOUNT, NEW.split(",")[1], TID, OID, "active")]:
        fail("NORMAL_ACCOUNT_ENTRA_BINDING_DIFFERENT")


def sources() -> None:
    if REPO.resolve() != pathlib.Path("/opt/jason/releases") / VERSION:
        fail("HOST_RELEASE_REVISION_CHANGED")
    st = DEPLOY.lstat()
    if (DEPLOY.is_symlink() or not stat.S_ISREG(st.st_mode)
            or st.st_uid != 0 or st.st_mode & 0o002 or sha(DEPLOY.read_bytes()) != DEPLOY_SHA256):
        fail("REVIEWED_DEPLOY_SOURCE_CHANGED")


def live(allowed: str = OLD) -> dict[str, Any]:
    sources()
    freeze()
    account()
    current = docker(LIVE)
    runtime = docker("jason-runtime")
    if current.get("State", {}).get("Running") is not True:
        fail("MCP_NOT_RUNNING")
    if current.get("Image") != IMAGE:
        fail("MCP_IMAGE_CHANGED")
    if current["Config"]["Labels"].get("com.teamaot.jason.source_revision") != VERSION:
        fail("MCP_REVISION_CHANGED")
    if runtime["Config"]["Labels"].get("com.teamaot.jason.source_revision") != VERSION:
        fail("RUNTIME_REVISION_CHANGED")
    if (runtime.get("State", {}).get("Health") or {}).get("Status") != "healthy":
        fail("RUNTIME_NOT_HEALTHY")
    if environment(current).get(KEY) != allowed:
        fail("OWNER_ALLOWLIST_CHANGED")
    return current


def other_config_unchanged(old: dict[str, Any], new: dict[str, Any]) -> None:
    before = environment(old)
    after = environment(new)
    if before.get(KEY) != OLD or after.get(KEY) != NEW:
        fail("OWNER_ALLOWLIST_READBACK_FAIL")
    a = {k: v for k, v in before.items() if k != KEY}
    b = {k: v for k, v in after.items() if k != KEY}
    if a != b:
        fail("UNRELATED_ENVIRONMENT_CHANGED")
    if old["Image"] != new["Image"]:
        fail("IMAGE_REPLACED")
    for key in ("User", "WorkingDir", "Entrypoint", "Cmd", "Labels",
                "Healthcheck", "ExposedPorts", "StopSignal", "StopTimeout"):
        if old["Config"].get(key) != new["Config"].get(key):
            fail("UNRELATED_CONFIG_CHANGED:" + key)
    for key in ("Privileged", "ReadonlyRootfs", "CapDrop", "CapAdd",
                "SecurityOpt", "Tmpfs", "PortBindings", "RestartPolicy",
                "LogConfig", "NetworkMode"):
        if old["HostConfig"].get(key) != new["HostConfig"].get(key):
            fail("UNRELATED_SECURITY_OR_PORT_CHANGE:" + key)
    def mounts(obj: dict[str, Any]) -> list[tuple]:
        return sorted((v.get("Type"), v.get("Source"), v.get("Destination"), v.get("RW"))
                      for v in obj.get("Mounts") or [])
    if mounts(old) != mounts(new):
        fail("UNRELATED_MOUNTS_CHANGED")
    networks = lambda o: sorted((o.get("NetworkSettings") or {}).get("Networks", {}).keys())
    if networks(old) != networks(new):
        fail("NETWORK_MEMBERSHIP_CHANGED")
    for name in networks(old):
        before_net = old["NetworkSettings"]["Networks"][name]
        after_net = new["NetworkSettings"]["Networks"][name]
        for field in ("Aliases", "Links", "DriverOpts"):
            if before_net.get(field) != after_net.get(field):
                fail("NETWORK_OPTION_CHANGED:" + field)


def record(folder: pathlib.Path, name: str, content: dict) -> None:
    path = folder / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(content, out, sort_keys=True, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())


def rollback(original: dict[str, Any]) -> None:
    if cmd("docker", "inspect", LIVE, check=False):
        cmd("docker", "rm", "-f", LIVE, timeout=60)
    prior = docker(ROLLBACK)
    if prior["Id"] != original["Id"]:
        fail("ROLLBACK_ORIGINAL_ID_MISMATCH")
    cmd("docker", "rename", ROLLBACK, LIVE)
    cmd("docker", "start", LIVE, timeout=60)
    restored = live(OLD)
    if restored["Id"] != original["Id"]:
        fail("ROLLBACK_READBACK_MISMATCH")


def do_apply(expected_tool_sha: str) -> None:
    if (os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al"
            or not os.isatty(0) or not os.isatty(1)
            or int(os.environ.get("SUDO_UID", "-1")) != pwd.getpwnam("al").pw_uid):
        fail("LOCAL_INDIVIDUAL_OWNER_SUDO_TTY_REQUIRED")
    actual_sha = sha(pathlib.Path(__file__).read_bytes())
    if expected_tool_sha != actual_sha:
        fail("REVIEWED_TOOL_SHA256_MISMATCH")
    if ROLLBACK in cmd("docker", "ps", "-a", "--format", "{{.Names}}").splitlines():
        fail("EXISTING_ROLLBACK_NAME_COLLISION")
    # Same transaction lock inode used by the native production release manager.
    st = LOCK.lstat()
    if LOCK.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_uid != pwd.getpwnam("al").pw_uid:
        fail("UNTRUSTED_PRODUCTION_TRANSACTION_LOCK")
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = live(OLD)
        # Re-run the reviewed native deployment preflight under the lock.
        preflight = [
            "/usr/bin/python3", str(DEPLOY),
            "--live", LIVE, "--image", IMAGE, "--rollback", ROLLBACK,
            "--source-revision", VERSION, "--health-url", "http://127.0.0.1:8000/healthz",
            "--harden", "--set-env", KEY + "=" + NEW, "--preflight",
        ]
        if "PREFLIGHT=PASS" not in cmd(*preflight, timeout=45):
            fail("NATIVE_SAME_IMAGE_PREFLIGHT_FAILED")
        # First prove all review expectations, then demand a fresh local human challenge.
        print("OPERATION=ONE_TIME_CONFIG_ONLY_MCP_OWNER_ALLOWLIST", flush=True)
        print("EXPECTED_SCOPE_SHA256=" + DIGEST, flush=True)
        phrase = "AUTHORIZE OWNER ALLOWLIST " + DIGEST[:16]
        print("Type exactly: " + phrase, flush=True)
        if input("> ").strip() != phrase:
            fail("OWNER_APPROVAL_CHALLENGE_MISMATCH")
        # Re-check unchanged authority inputs after the typed human authorization.
        fresh = live(OLD)
        if fresh["Id"] != original["Id"]:
            fail("LIVE_CONTAINER_CHANGED_DURING_APPROVAL")
        if not AUDIT.is_dir() or AUDIT.is_symlink() or AUDIT.stat().st_uid != 0 or AUDIT.stat().st_mode & 0o022:
            fail("ROOT_AUDIT_DIRECTORY_UNTRUSTED")
        folder = pathlib.Path(tempfile.mkdtemp(prefix="owner-exact-mcp-allowlist-", dir=AUDIT))
        os.chown(folder, 0, 0)
        os.chmod(folder, 0o700)
        record(folder, "intent.json", {
            "operation": SCOPE, "scope_sha256": DIGEST,
            "approved_by_local_sudo_user": "al",
            "script_sha256": actual_sha, "original_container_id": original["Id"],
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "freeze_sha256_before": FREEZE_SHA256,
            "external_audit_custody_required": True,
        })
        print("OWNER_AUDIT_INTENT=RECORDED", flush=True)
        command = [
            "/usr/bin/python3", str(DEPLOY),
            "--live", LIVE, "--image", IMAGE, "--rollback", ROLLBACK,
            "--source-revision", VERSION, "--health-url", "http://127.0.0.1:8000/healthz",
            "--harden", "--set-env", KEY + "=" + NEW,
        ]
        try:
            cmd(*command, timeout=180)
            new = live(NEW)
            other_config_unchanged(original, new)
            old = docker(ROLLBACK)
            if old["Id"] != original["Id"] or old["State"]["Running"] is not False:
                fail("ORIGINAL_ROLLBACK_CONTAINER_UNVERIFIED")
            record(folder, "result.json", {
                "status": "verified_applied",
                "scope_sha256": DIGEST,
                "new_container_id": new["Id"],
                "original_rollback_id": old["Id"],
                "source_revision": VERSION, "image_digest": IMAGE,
                "freeze_sha256_after": sha(FREEZE.read_bytes()),
                "all_other_configuration_unchanged": True,
                "external_audit_custody_required": True,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            })
            print("MAINTENANCE_STATUS=VERIFIED_APPLIED")
            print("FREEZE_UNCHANGED=PASS")
            print("NO_CODE_MERGE_OR_NEW_IMAGE=PASS")
            print("AUDIT_DIRECTORY=" + str(folder))
        except Exception as err:
            print("MAINTENANCE_STATUS=FAILED_ROLLBACK_REQUIRED", flush=True)
            try:
                if ROLLBACK in cmd("docker", "ps", "-a", "--format", "{{.Names}}").splitlines():
                    rollback(original)
                    record(folder, "result.json", {
                        "status": "rolled_back",
                        "original_container_id": original["Id"],
                        "freeze_sha256_after": sha(FREEZE.read_bytes()),
                        "failure_type": type(err).__name__,
                    })
                    print("ROLLBACK=VERIFIED", flush=True)
                else:
                    print("ROLLBACK=NOT_NEEDED_OR_ATTEMPTED_BY_NATIVE_HELPER", flush=True)
                    live(OLD)
            except Exception as recovery_error:
                print("ROLLBACK=REQUIRES_HUMAN_INTERVENTION:" + type(recovery_error).__name__, flush=True)
            raise
        finally:
            freeze()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-tool-sha256", default="")
    args = parser.parse_args()
    if args.review == args.apply:
        fail("CHOOSE_EXACTLY_ONE_MODE")
    if args.review:
        current = live(OLD)
        print(json.dumps({
            "status": "review_only", "no_mutations": True,
            "expected_source_revision": VERSION, "image_digest": IMAGE,
            "owner_allowlist_current": OLD, "owner_allowlist_proposed": NEW,
            "other_configuration_unchanged": True,
            "freeze_sha256": FREEZE_SHA256,
            "scope_sha256": DIGEST,
            "original_container_id": current["Id"],
            "requires_human_local_sudo_approval": True,
        }, sort_keys=True))
    else:
        if len(args.expected_tool_sha256) != 64:
            fail("EXPECTED_TOOL_SHA256_REQUIRED")
        do_apply(args.expected_tool_sha256)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DENIED:" + str(exc)[:250], file=sys.stderr)
        sys.exit(2)
