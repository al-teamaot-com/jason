"""One-shot, root-trusted recovery of the existing MCP Owner signer bind.

Source only until a separately authorized root installation places both this module
and the exact policy at root-owned, non-writable paths. Never run this from a
writable Git worktree as root. Entra sign-in is interactive and independently
verified; chat text, a local JSON approval, and prior release proofs are invalid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import jwt
from jwt import PyJWKClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

LKG = "690250b4d21f32cce79cab9f5b4c18cf93e7e94a"
MCP_IMAGE = "sha256:5ef62c30c35e98ca631b2fc8ea2a38a8b574a38e21f3423f4fe1f2ff09e0c16d"
RUNTIME_IMAGE = "sha256:186977467897e6944f5c5f0d51c0d465b3515174c44fda1e390ccd5d2b18bff7"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
PUBLIC_SHA = "1e1f5a8d4098b57ca8bf7532b60f35950bbfd7eca22ee24ae37a89825d169840"
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
CLIENT_ID = "9b9996e9-5c34-48b7-948c-f44f89352f89"
SCOPE = "https://mcp-jason.teamaot.com/mcp/Jason.Read"
OWNERS = frozenset((
    "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
    "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
))
DEST = "/run/jason-secrets/owner-release/private_key"
PRIVATE = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
TRUST = Path("/etc/jason-owner-release/verified-owner-public-key.json")
POLICY = Path("/etc/jason-owner-release/owner-signer-recovery-policy.json")
SCRIPT_INSTALLED = Path("/usr/local/lib/jason/owner_signer_recovery.py")
LEDGER_DIR = Path("/etc/jason-owner-release/owner-signer-recovery-ledger")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
DEPLOYER = Path("/opt/jason/current/tools/deploy_live_container.py")
OPERATION = "owner-signer-reattach-690250b4-v1"
MCP = "jason-mcp-pilot"
BACKUP = "jason-mcp-signer-recovery-prior"
URL = "http://127.0.0.1:8000/healthz"


class RecoveryDenied(PermissionError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def root_file(path: Path, *, maximum: int = 32768,
              allow_mutable_parent: bool = False) -> bytes:
    # Open first, then validate the OPEN file descriptor: a check-then-open
    # on root-owned files in the legacy al-owned spool is not race safe.
    parent = path.parent.lstat()
    if (path.parent.is_symlink() or (not allow_mutable_parent and
            (parent.st_uid != 0 or parent.st_mode & 0o022))):
        raise RecoveryDenied("ROOT_TRUST_PARENT_UNSAFE")
    if path.is_symlink():
        raise RecoveryDenied("ROOT_TRUST_PATH_SYMLINK")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RecoveryDenied("ROOT_TRUST_OPEN_DENIED") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or info.st_size > maximum):
            raise RecoveryDenied("ROOT_TRUST_PATH_UNSAFE:" + str(path))
        raw = os.read(fd, maximum + 1)
        if len(raw) > maximum or len(raw) != info.st_size:
            raise RecoveryDenied("ROOT_TRUST_SIZE_CHANGED")
        return raw
    finally:
        os.close(fd)


def run_json(*args: str) -> dict:
    result = subprocess.check_output(args, text=True, timeout=20, stderr=subprocess.DEVNULL)
    value = json.loads(result)
    if isinstance(value, list):
        if len(value) != 1:
            raise RecoveryDenied("DOCKER_INSPECT_CARDINALITY")
        return value[0]
    if not isinstance(value, dict):
        raise RecoveryDenied("JSON_OBJECT_REQUIRED")
    return value


def docker(name: str) -> dict:
    return run_json("docker", "inspect", name)


def env_map(container: dict) -> dict[str, str]:
    values = {}
    for entry in container.get("Config", {}).get("Env") or []:
        if isinstance(entry, str) and "=" in entry:
            key, value = entry.split("=", 1)
            values[key] = value
    return values


def trusted_signer() -> str:
    info = PRIVATE.lstat()
    user = pwd.getpwnam("al")
    if (PRIVATE.is_symlink() or info.st_uid != user.pw_uid or
            not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o400 or
            info.st_size != 32):
        raise RecoveryDenied("PRIVATE_SIGNER_SECURITY_INVALID")
    raw = PRIVATE.read_bytes()
    pub = Ed25519PrivateKey.from_private_bytes(raw).public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )
    digest = sha(pub)
    root_policy = json.loads(root_file(TRUST))
    authorized = root_policy.get("authorized_owner_subjects") or []
    owner_ids = {str(item.get("owner_oid") or "").lower()
                 for item in authorized if isinstance(item, dict)}
    if (root_policy.get("public_key_sha256") != PUBLIC_SHA or
            digest != PUBLIC_SHA or owner_ids != OWNERS or
            root_policy.get("standing_authority") is not False or
            root_policy.get("tenant_id") != TENANT):
        raise RecoveryDenied("ROOT_PINNED_PUBLIC_TRUST_MISMATCH")
    return digest


def host_release() -> Path:
    return Path("/opt/jason/current").resolve(strict=True)


def mount_inventory(container: dict) -> list:
    return sorted(
        (str(x.get("Type")), str(x.get("Source")),
         str(x.get("Destination")), bool(x.get("RW")))
        for x in container.get("Mounts", [])
    )


def evidence(*, strict: bool = True) -> dict:
    # Check the actual root-owned control, not the unprivileged published snapshot.
    if strict:
        # The existing root control files sit under an al-owned spool. The
        # files themselves MUST be root-owned 0600 and nonsymlinks: al can
        # delete but cannot forge a replacement with root ownership.
        control = json.loads(root_file(CONTROL, maximum=131072,
                                      allow_mutable_parent=True))
        drift = json.loads(root_file(DRIFT, maximum=131072,
                                    allow_mutable_parent=True))
    else:
        snap = CONTROL.parent / "protected-readback"
        control = json.loads((snap / "production-control-state.json").read_bytes())
        drift = json.loads((snap / "production-drift.json").read_bytes())
    manifest = ((control.get("last_known_good") or {}).get("manifest") or {})
    breaker = control.get("circuit_breaker") or {}
    if breaker.get("state") != "closed" or manifest.get("complete") is not True:
        raise RecoveryDenied("ROOT_BREAKER_OR_LKG_UNVERIFIED")
    if any(manifest.get(key) != expected for key, expected in (
        ("revision", LKG), ("runtime_revision", LKG),
        ("mcp_revision", LKG), ("host_revision", LKG),
        ("runtime_image_id", RUNTIME_IMAGE), ("mcp_image_id", MCP_IMAGE),
    )):
        raise RecoveryDenied("IMMUTABLE_LKG_MANIFEST_MISMATCH")
    when = datetime.fromisoformat(str(drift.get("observed_at", "")).replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - when).total_seconds()
    if (drift.get("status") != "pass" or drift.get("problems") != []
            or when.tzinfo is None or not -10 <= age <= 180):
        raise RecoveryDenied("ROOT_DRIFT_NOT_FRESH_CLEAN")
    if sha(FREEZE.read_bytes()) != FREEZE_SHA:
        raise RecoveryDenied("FREEZE_BYTES_MISMATCH")
    current = host_release()
    if current != Path("/opt/jason/releases") / LKG:
        raise RecoveryDenied("HOST_LKG_SYMLINK_MISMATCH")
    runtime = docker("jason-runtime")
    mcp = docker(MCP)
    if (runtime.get("Image") != RUNTIME_IMAGE
            or mcp.get("Image") != MCP_IMAGE
            or runtime.get("State", {}).get("Health", {}).get("Status") != "healthy"
            or mcp.get("State", {}).get("Status") != "running"):
        raise RecoveryDenied("LIVE_IMAGE_OR_HEALTH_MISMATCH")
    for item in (runtime, mcp):
        labels = item.get("Config", {}).get("Labels") or {}
        if labels.get("com.teamaot.jason.source_revision") != LKG:
            raise RecoveryDenied("LIVE_REVISION_LABEL_MISMATCH")
    current_env = env_map(mcp)
    if current_env.get("JASON_OWNER_RELEASE_ED25519_KEY_PATH", "") not in ("", DEST):
        raise RecoveryDenied("UNEXPECTED_MCP_SIGNER_ENV")
    existing_signer = [x for x in mcp.get("Mounts", []) if x.get("Destination") == DEST]
    if existing_signer:
        raise RecoveryDenied("SIGNER_MOUNT_ALREADY_PRESENT")
    if any(x.get("Destination") == DEST for x in runtime.get("Mounts", [])):
        raise RecoveryDenied("SIGNER_MOUNT_ON_RUNTIME_FORBIDDEN")
    prior_env = dict(current_env)
    prior_env.pop("JASON_OWNER_RELEASE_ED25519_KEY_PATH", None)
    return {
        "operation": OPERATION, "mcp_container_id": mcp["Id"],
        "mcp_image": mcp["Image"], "runtime_container_id": runtime["Id"],
        "freeze_sha256": FREEZE_SHA, "observed_at": when.isoformat(),
        "original_env": prior_env,
        "original_mounts": mount_inventory(mcp),
        "original_networks": sorted((mcp.get("NetworkSettings", {}).get("Networks") or {}).keys()),
        "original_user": mcp.get("Config", {}).get("User"),
    }


def postcheck(pre: dict) -> dict:
    current = docker(MCP)
    if current.get("Id") == pre["mcp_container_id"] or current.get("Image") != MCP_IMAGE:
        raise RecoveryDenied("MCP_EXACT_REPLACEMENT_NOT_VERIFIED")
    if env_map(current).get("JASON_OWNER_RELEASE_ED25519_KEY_PATH") != DEST:
        raise RecoveryDenied("SIGNER_ENV_NOT_RESTORED")
    matched = [
        x for x in current.get("Mounts", [])
        if x.get("Destination") == DEST and x.get("Source") == str(PRIVATE)
        and x.get("Type") == "bind" and x.get("RW") is False
    ]
    if len(matched) != 1:
        raise RecoveryDenied("READONLY_SIGNER_BIND_NOT_VERIFIED")
    if "original_mounts" in pre:
        expected_mounts = sorted(pre["original_mounts"] + [
            ("bind", str(PRIVATE), DEST, False)
        ])
        if mount_inventory(current) != expected_mounts:
            raise RecoveryDenied("UNRELATED_MCP_MOUNT_DRIFT")
    if "original_env" in pre:
        env = env_map(current)
        env.pop("JASON_OWNER_RELEASE_ED25519_KEY_PATH", None)
        if env != pre["original_env"]:
            raise RecoveryDenied("UNRELATED_MCP_ENV_DRIFT")
    if "original_networks" in pre and sorted(
            (current.get("NetworkSettings", {}).get("Networks") or {}).keys()
    ) != pre["original_networks"]:
        raise RecoveryDenied("MCP_NETWORK_TOPOLOGY_CHANGED")
    if "original_user" in pre and current.get("Config", {}).get("User") != pre["original_user"]:
        raise RecoveryDenied("MCP_USER_CHANGED")
    if (current.get("HostConfig", {}).get("Privileged") is True
            or current.get("HostConfig", {}).get("ReadonlyRootfs") is not True
            or "ALL" not in (current.get("HostConfig", {}).get("CapDrop") or [])):
        raise RecoveryDenied("MCP_SANDBOX_HARDENING_LOST")
    if current.get("State", {}).get("Status") != "running":
        raise RecoveryDenied("MCP_NOT_RUNNING")
    # The private bytes never cross process output; only a matching public digest is emitted.
    probe = (
        "import hashlib;from cryptography.hazmat.primitives.asymmetric.ed25519 "
        "import Ed25519PrivateKey;from cryptography.hazmat.primitives.serialization "
        "import Encoding,PublicFormat;from pathlib import Path;"
        "raw=Path('/run/jason-secrets/owner-release/private_key').read_bytes();"
        "assert len(raw)==32;"
        "pub=Ed25519PrivateKey.from_private_bytes(raw).public_key().public_bytes("
        "encoding=Encoding.Raw,format=PublicFormat.Raw);"
        "print(hashlib.sha256(pub).hexdigest())"
    )
    digest = subprocess.check_output(
        ["docker", "exec", MCP, "python", "-c", probe],
        text=True, timeout=15, stderr=subprocess.DEVNULL
    ).strip()
    if digest != PUBLIC_SHA:
        raise RecoveryDenied("IN_CONTAINER_SIGNER_PUBLIC_MISMATCH")
    if sha(FREEZE.read_bytes()) != FREEZE_SHA:
        raise RecoveryDenied("FREEZE_CHANGED")
    if docker("jason-runtime")["Id"] != pre["runtime_container_id"]:
        raise RecoveryDenied("RUNTIME_CONTAINER_CHANGED")
    control = json.loads(root_file(CONTROL, maximum=131072,
                                   allow_mutable_parent=True))
    drift = json.loads(root_file(DRIFT, maximum=131072,
                                 allow_mutable_parent=True))
    if (control.get("circuit_breaker", {}).get("state") != "closed" or
            control.get("last_known_good", {}).get("manifest", {}).get("revision") != LKG or
            drift.get("status") != "pass" or drift.get("problems") != []):
        raise RecoveryDenied("ROOT_POLICY_OR_DRIFT_CHANGED_DURING_RECOVERY")
    trusted_signer()
    return {"new_mcp_container_id": current["Id"], "verified": True}


def jwt_owner(token: str) -> str:
    jwks = "https://login.microsoftonline.com/" + TENANT + "/discovery/v2.0/keys"
    key = PyJWKClient(jwks).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token, key.key, algorithms=["RS256"], audience=CLIENT_ID,
        issuer="https://login.microsoftonline.com/" + TENANT + "/v2.0",
        leeway=60, options={"require": ["iss", "aud", "exp", "iat", "nbf", "oid", "tid"]},
    )
    oid = str(claims.get("oid") or "").lower()
    scopes = str(claims.get("scp") or "").split()
    if claims.get("tid") != TENANT or oid not in OWNERS or "Jason.Read" not in scopes:
        raise RecoveryDenied("ENTRA_OWNER_SCOPE_OR_TENANT_DENIED")
    return oid


def _form(url: str, params: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read(8192))
    except urllib.error.HTTPError as err:
        try:
            return json.loads(err.read(8192))
        except Exception as exc:
            raise RecoveryDenied("ENTRA_RESPONSE_INVALID") from exc


def interactive_owner() -> str:
    root = "https://login.microsoftonline.com/" + TENANT + "/oauth2/v2.0/"
    spec = _form(root + "devicecode", {"client_id": CLIENT_ID, "scope": SCOPE})
    if not all(isinstance(spec.get(k), str) for k in ("device_code", "user_code", "verification_uri")):
        raise RecoveryDenied("ENTRA_DEVICE_FLOW_UNAVAILABLE:" + str(spec.get("error", "invalid"))[:80])
    ttl = min(int(spec.get("expires_in", 0)), 600)
    if ttl < 60:
        raise RecoveryDenied("ENTRA_DEVICE_CODE_LIFETIME_INVALID")
    print("EXACT_ACTION=" + OPERATION, flush=True)
    print("LKG_SOURCE_SHA=" + LKG, flush=True)
    print("FREEZE_SHA256=" + FREEZE_SHA, flush=True)
    print("AUTHORIZE_ONLY_ONE_READONLY_MCP_OWNER_SIGNER_BIND=true", flush=True)
    print("BROWSER_VERIFICATION_URL=" + spec["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + spec["user_code"], flush=True)
    deadline = time.monotonic() + ttl
    interval = max(5, int(spec.get("interval", 5)))
    while time.monotonic() < deadline:
        time.sleep(interval)
        result = _form(root + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": CLIENT_ID, "device_code": spec["device_code"],
        })
        if isinstance(result.get("access_token"), str):
            return jwt_owner(result["access_token"])
        status = str(result.get("error") or "")
        if status == "authorization_pending":
            continue
        if status == "slow_down":
            interval = min(interval + 5, 20)
            continue
        raise RecoveryDenied("ENTRA_OWNER_AUTHORIZATION_FAILED:" + status[:80])
    raise RecoveryDenied("ENTRA_OWNER_AUTHORIZATION_EXPIRED")


def write_root_record(path: Path, record: dict) -> None:
    data = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        os.fchown(fd, 0, 0)
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def execute() -> None:
    if os.geteuid() != 0:
        raise RecoveryDenied("ROOT_NATIVE_EXECUTION_REQUIRED")
    if sys.flags.isolated != 1:
        raise RecoveryDenied("ISOLATED_PYTHON_ROOT_EXECUTION_REQUIRED")
    if SCRIPT_INSTALLED.resolve() != Path(__file__).resolve():
        raise RecoveryDenied("MUST_RUN_INSTALLED_ROOT_TRUSTED_SCRIPT")
    installed_source = root_file(SCRIPT_INSTALLED, maximum=100000)
    policy = json.loads(root_file(POLICY))
    expected = {
        "schema_version": "1.0", "operation": OPERATION, "one_shot": True,
        "lkg_sha": LKG, "mcp_image_sha256": MCP_IMAGE,
        "runtime_image_sha256": RUNTIME_IMAGE, "freeze_sha256": FREEZE_SHA,
        "signer_public_sha256": PUBLIC_SHA,
        "owner_authentication": "fresh_verified_entra_device_code",
        "native_deployer": str(DEPLOYER),
        "script_sha256": policy.get("script_sha256"),
        "native_deployer_sha256": policy.get("native_deployer_sha256"),
    }
    if policy != expected:
        raise RecoveryDenied("ROOT_INSTALLED_POLICY_SCOPE_MISMATCH")
    if (not re.fullmatch(r"[0-9a-f]{64}", str(policy["script_sha256"])) or
            not re.fullmatch(r"[0-9a-f]{64}", str(policy["native_deployer_sha256"])) or
            sha(installed_source) != policy["script_sha256"] or
            sha(root_file(DEPLOYER, maximum=100000)) != policy["native_deployer_sha256"]):
        raise RecoveryDenied("REVIEWED_SOURCE_OR_NATIVE_DEPLOYER_HASH_MISMATCH")
    if not LEDGER_DIR.exists():
        raise RecoveryDenied("ROOT_RECOVERY_LEDGER_NOT_INSTALLED")
    ls = LEDGER_DIR.lstat()
    if LEDGER_DIR.is_symlink() or ls.st_uid != 0 or stat.S_IMODE(ls.st_mode) != 0o700:
        raise RecoveryDenied("ROOT_RECOVERY_LEDGER_UNSAFE")
    if list(LEDGER_DIR.glob(OPERATION + "*")):
        raise RecoveryDenied("RECOVERY_ALREADY_ATTEMPTED_ONE_SHOT")
    trusted_signer()
    pre = evidence(strict=True)
    # Operator is independently authenticated by Entra, NOT inferred from chat or sudo.
    owner_oid = interactive_owner()
    trusted_signer()
    if evidence(strict=True)["mcp_container_id"] != pre["mcp_container_id"]:
        raise RecoveryDenied("LIVE_STATE_CHANGED_DURING_AUTHORIZATION")
    attempt = LEDGER_DIR / (OPERATION + ".attempt.json")
    write_root_record(attempt, {
        "schema_version": "1.0", "operation": OPERATION,
        "owner_oid": owner_oid, "production_lkg_sha": LKG,
        "mcp_container_before": pre["mcp_container_id"],
        "freeze_sha256": FREEZE_SHA,
        "when_utc": datetime.now(timezone.utc).isoformat(),
        "root_reviewed_source_sha256": policy["script_sha256"],
        "native_deployer_sha256": policy["native_deployer_sha256"],
        "approval_method": "fresh_entra_device_code_verified_jwks",
        "one_release_only": True,
        "standing_authority": False,
        "state": "one_shot_claimed",
    })
    command = [
        sys.executable, str(DEPLOYER),
        "--live", MCP, "--image", MCP_IMAGE,
        "--rollback", BACKUP, "--source-revision", LKG,
        "--health-url", URL, "--health-attempts", "10",
        "--health-interval", "2", "--harden",
        "--set-env", "JASON_OWNER_RELEASE_ED25519_KEY_PATH=" + DEST,
        "--add-readonly-bind", str(PRIVATE) + ":" + DEST,
    ]
    result = {"schema_version": "1.0", "operation": OPERATION, "outcome": "failed"}
    try:
        subprocess.run(command, check=True, timeout=180, stdout=subprocess.DEVNULL)
        after = postcheck(pre)
        if (docker("jason-runtime")["Id"] != pre["runtime_container_id"] or
                host_release() != Path("/opt/jason/releases") / LKG):
            raise RecoveryDenied("OTHER_PRODUCTION_COMPONENT_CHANGED")
        result.update({"outcome": "verified", **after})
    except Exception:
        # Native deployer itself rolls back failed replacements. If a postflight
        # gate fails AFTER native success, restore the exact prior named container.
        try:
            if subprocess.run(["docker", "inspect", BACKUP], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                subprocess.run(["docker", "rm", "-f", MCP], check=True,
                               stdout=subprocess.DEVNULL, timeout=40)
                subprocess.run(["docker", "rename", BACKUP, MCP], check=True, timeout=30)
                subprocess.run(["docker", "start", MCP], check=True,
                               stdout=subprocess.DEVNULL, timeout=40)
            result["rollback_to_old_mcp"] = (
                docker(MCP).get("Id") == pre["mcp_container_id"]
            )
        except Exception:
            result["rollback_to_old_mcp"] = False
        raise
    finally:
        result["when_utc"] = datetime.now(timezone.utc).isoformat()
        write_root_record(LEDGER_DIR / (OPERATION + ".result.json"), result)
    print("OWNER_SIGNER_RECOVERY=VERIFIED")
    print("MCP_IMAGE_ID=" + MCP_IMAGE)
    print("FREEZE_UNCHANGED=true")
    print("OWNER_AUTH=verified_entra_oauth")
    print("ONE_SHOT_AUDIT=" + str(attempt))


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-only", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.check_only:
            evidence(strict=False)
            trusted_signer()
            print("READ_ONLY_RECOVERY_PREFLIGHT=PASS")
            print("RECOVERY_EXECUTED=false")
        else:
            execute()
    except (RecoveryDenied, KeyError, ValueError, OSError, subprocess.SubprocessError,
            jwt.PyJWTError) as exc:
        print("OWNER_SIGNER_RECOVERY=DENIED " + type(exc).__name__ + ":" + str(exc)[:160],
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
