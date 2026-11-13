#!/usr/bin/env python3
"""One-use, same-image PMv4 Stage A0 Owner issuer activation (NOT self-installing).

Only a separately approved root-installed, hash-pinned copy may execute.
The active MCP image already contains the Stage A0 Owner issuer. This
transaction changes precisely one environment variable, never deploys a new
source revision or touches the ticket-processing runtime. The established
native Docker replacer owns the rollback container and health wait.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any, Mapping

ACTION = "pmv4-stage-a0-same-image-owner-issuer-v1"
FLAG = "JASON_PMV4_STAGE_A0_ISSUER_ENABLED"
INSTALLED = Path("/usr/local/lib/jason/pmv4_stage_a0_issuer_activation.py")
POLICY = Path("/etc/jason-owner-release/pmv4-stage-a0-issuer-activation.json")
LEDGER = Path("/etc/jason-owner-release/pmv4-stage-a0-issuer-ledger")
AUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
DEPLOYER = Path("/usr/local/lib/jason/deploy_live_container_owner_signer_2450.py")
OWNER_VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
SIGNER_KEY = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
PUBLIC_TRUST = Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
CURRENT = Path("/opt/jason/current")
RELEASES = Path("/opt/jason/releases")
LIVE = "jason-mcp-pilot"
RUNTIME = "jason-runtime"
ROLLBACK = "jason-mcp-rollback-pmv4-a0-issuer"
SIGNER_DEST = "/run/jason-secrets/owner-release/private_key"
SIGNER_SRC = "/var/lib/jason/runtime-secrets/owner-release/private_key"
SCHEMA = {
    "schema_version", "exact_action", "component", "one_shot",
    "source_sha", "mcp_image_sha256", "runtime_image_sha256",
    "freeze_sha256", "promotion_hold_sha256", "script_sha256",
    "trusted_auth_sha256", "native_deployer_sha256",
    "owner_release_verifier_sha256", "change",
    "owner_authentication", "production_services", "provider_writes",
}


class IssuerActivationDenied(PermissionError):
    pass


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def read_root_file(path: Path, *, max_bytes: int = 131072,
                   root_parent: bool = True) -> bytes:
    if path.is_symlink():
        raise IssuerActivationDenied("A0_UNTRUSTED_ROOT_SYMLINK")
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022
            or (root_parent and parent.st_uid != 0)):
        raise IssuerActivationDenied("A0_UNTRUSTED_ROOT_PARENT")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0
                or meta.st_mode & 0o022 or meta.st_nlink != 1
                or meta.st_size > max_bytes):
            raise IssuerActivationDenied("A0_UNTRUSTED_ROOT_FILE")
        raw = os.read(fd, max_bytes + 1)
        if len(raw) != meta.st_size:
            raise IssuerActivationDenied("A0_ROOT_FILE_CHANGED")
        return raw
    finally:
        os.close(fd)


def trusted_policy() -> dict[str, Any]:
    value = json.loads(read_root_file(POLICY, max_bytes=4096))
    if (not isinstance(value, dict) or set(value) != SCHEMA
            or value["schema_version"] != "1.0"
            or value["exact_action"] != ACTION
            or value["component"] != "pmv4-stage-a0-owner-issuer"
            or value["one_shot"] is not True
            or value["change"] != "same-mcp-image-one-env-flag-only"
            or value["owner_authentication"] != "fresh-entra-oauth-exact-action"
            or value["production_services"] != [LIVE]
            or value["provider_writes"] is not False
            or not isinstance(value["source_sha"], str)
            or len(value["source_sha"]) != 40
            or any(ch not in "0123456789abcdef" for ch in value["source_sha"])):
        raise IssuerActivationDenied("A0_ISSUER_POLICY_INVALID")
    for key in ("mcp_image_sha256", "runtime_image_sha256"):
        item = value[key]
        if (not isinstance(item, str) or not item.startswith("sha256:")
                or len(item) != 71 or any(x not in "0123456789abcdef" for x in item[7:])):
            raise IssuerActivationDenied("A0_ISSUER_IMAGE_POLICY_INVALID")
    for key, path in (
        ("script_sha256", INSTALLED),
        ("trusted_auth_sha256", AUTH),
        ("native_deployer_sha256", DEPLOYER),
        ("owner_release_verifier_sha256", OWNER_VERIFIER),
    ):
        expected = value[key]
        if (not isinstance(expected, str) or len(expected) != 64
                or digest(read_root_file(path)) != expected):
            raise IssuerActivationDenied("A0_ISSUER_EXECUTABLE_DRIFT")
    for key in ("freeze_sha256", "promotion_hold_sha256"):
        item = value[key]
        if not isinstance(item, str) or len(item) != 64:
            raise IssuerActivationDenied("A0_ISSUER_PROTECTED_DIGEST_INVALID")
    return value


def docker(name: str) -> dict[str, Any]:
    output = subprocess.check_output(["docker", "inspect", name], text=True, timeout=15)
    values = json.loads(output)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise IssuerActivationDenied("A0_DOCKER_INSPECT_INVALID")
    return values[0]


def env_map(obj: Mapping[str, Any]) -> dict[str, str]:
    result = {}
    for item in obj.get("Config", {}).get("Env") or []:
        if not isinstance(item, str) or "=" not in item:
            raise IssuerActivationDenied("A0_MCP_ENV_INVALID")
        key, value = item.split("=", 1)
        if key in result:
            raise IssuerActivationDenied("A0_MCP_ENV_DUPLICATE")
        result[key] = value
    return result


def mounts(obj: Mapping[str, Any]) -> list[tuple[str, str, str, bool]]:
    return sorted((
        str(m["Type"]), str(m["Source"]), str(m["Destination"]), bool(m["RW"])
    ) for m in obj.get("Mounts") or [])


def networks(obj: Mapping[str, Any]) -> list[str]:
    return sorted((obj.get("NetworkSettings", {}).get("Networks") or {}).keys())


def snapshot(policy: Mapping[str, Any]) -> dict[str, Any]:
    control = json.loads(read_root_file(CONTROL, root_parent=False))
    drift = json.loads(read_root_file(DRIFT, root_parent=False))
    lkg = (control.get("last_known_good") or {}).get("manifest") or {}
    if (control.get("circuit_breaker", {}).get("state") != "closed"
            or lkg.get("complete") is not True or drift.get("status") != "pass"
            or drift.get("problems") != []):
        raise IssuerActivationDenied("A0_BREAKER_OR_DRIFT_NOT_CLEAR")
    stamp = datetime.fromisoformat(str(drift.get("observed_at") or "").replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    if stamp.tzinfo is None or age < -10 or age > 180:
        raise IssuerActivationDenied("A0_DRIFT_NOT_FRESH")
    source = policy["source_sha"]
    for key, expected in (
        ("revision", source), ("runtime_revision", source),
        ("mcp_revision", source), ("host_revision", source),
        ("runtime_image_id", policy["runtime_image_sha256"]),
        ("mcp_image_id", policy["mcp_image_sha256"]),
    ):
        if lkg.get(key) != expected:
            raise IssuerActivationDenied("A0_LKG_PROTECTION_CHANGED:" + key)
    if (CURRENT.resolve(strict=True) != RELEASES / source
            or digest(FREEZE.read_bytes()) != policy["freeze_sha256"]
            or digest(HOLD.read_bytes()) != policy["promotion_hold_sha256"]):
        raise IssuerActivationDenied("A0_FREEZE_HOLD_OR_SOURCE_CHANGED")
    runtime, mcp = docker(RUNTIME), docker(LIVE)
    if (runtime.get("Image") != policy["runtime_image_sha256"]
            or mcp.get("Image") != policy["mcp_image_sha256"]
            or runtime.get("State", {}).get("Health", {}).get("Status") != "healthy"
            or mcp.get("State", {}).get("Status") != "running"):
        raise IssuerActivationDenied("A0_CONTAINER_HEALTH_OR_IMAGE_MISMATCH")
    for obj in (runtime, mcp):
        if (obj.get("Config", {}).get("Labels") or {}).get("com.teamaot.jason.source_revision") != source:
            raise IssuerActivationDenied("A0_CONTAINER_REVISION_DRIFT")
    sandbox = mcp.get("HostConfig") or {}
    if (sandbox.get("ReadonlyRootfs") is not True
            or sandbox.get("Privileged") is True
            or "ALL" not in (sandbox.get("CapDrop") or [])):
        raise IssuerActivationDenied("A0_MCP_SECURITY_REGRESSION")
    emap = env_map(mcp)
    if (emap.get(FLAG) != "false"
            or emap.get("JASON_OWNER_RELEASE_ED25519_KEY_PATH") != SIGNER_DEST
            or emap.get("JASON_PMV4_OWNER_ISSUER_ENABLED") != "false"):
        raise IssuerActivationDenied("A0_UNRELATED_OWNER_AUTHORITY_OR_ALREADY_ENABLED")
    if ("bind", SIGNER_SRC, SIGNER_DEST, False) not in mounts(mcp):
        raise IssuerActivationDenied("A0_SIGNER_BIND_MISSING_OR_WRITABLE")
    return {
        "mcp_id": mcp["Id"], "runtime_id": runtime["Id"],
        "mcp": mcp, "env": emap, "mounts": mounts(mcp),
        "networks": networks(mcp), "source_sha": source,
    }


def verify_changed_only_one_flag(before: Mapping[str, Any],
                                 after: Mapping[str, Any]) -> None:
    if (after.get("Image") != before["mcp"]["Image"]
            or after.get("Id") == before["mcp_id"]
            or after.get("State", {}).get("Status") != "running"
            or after.get("Config", {}).get("User") != before["mcp"]["Config"].get("User")
            or mounts(after) != before["mounts"]
            or networks(after) != before["networks"]):
        raise IssuerActivationDenied("A0_MCP_REPLACEMENT_OR_MOUNT_DRIFT")
    new = dict(before["env"])
    new[FLAG] = "true"
    if env_map(after) != new:
        raise IssuerActivationDenied("A0_MCP_CHANGED_MORE_THAN_EXACT_FLAG")
    for prop in ("ReadonlyRootfs", "Privileged", "CapDrop", "SecurityOpt"):
        if (after.get("HostConfig") or {}).get(prop) != (
                before["mcp"].get("HostConfig") or {}).get(prop):
            raise IssuerActivationDenied("A0_MCP_SANDBOX_CHANGED:" + prop)
    if (after["Config"].get("Labels") or {}) != (
            before["mcp"]["Config"].get("Labels") or {}):
        raise IssuerActivationDenied("A0_MCP_IMAGE_LABELS_CHANGED")


@contextmanager
def old_release_lock():
    fd = os.open(LOCK, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                or meta.st_uid != 1000 or stat.S_IMODE(meta.st_mode) != 0o664):
            raise IssuerActivationDenied("A0_SHARED_RELEASE_LOCK_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise IssuerActivationDenied("A0_SHARED_RELEASE_LOCK_BUSY") from exc
        yield
    finally:
        os.close(fd)


def atomic_record(path: Path, value: Mapping[str, Any]) -> None:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchown(fd, 0, 0)
        if os.write(fd, data) != len(data):
            raise IssuerActivationDenied("A0_AUDIT_WRITE_INCOMPLETE")
        os.fsync(fd)
    finally:
        os.close(fd)


def action_scope_sha256(policy: Mapping[str, Any]) -> str:
    """Bind the Owner signature to the *one* MCP environment mutation."""
    selected = {
        "schema_version": "1.0", "action": ACTION,
        "source_sha": policy["source_sha"],
        "runtime_image": policy["runtime_image_sha256"],
        "mcp_image": policy["mcp_image_sha256"],
        "flag": FLAG + "=true",
        "rollback": "same-image-original-container-issuer-off",
        "provider_writes": False,
        "core_mutation": False,
    }
    return digest(json.dumps(selected, sort_keys=True,
                             separators=(",", ":")).encode())


def issue_bound_proof(owner_oid: str, policy: Mapping[str, Any],
                      *, module: Any, signer: Any, trust: Any,
                      at: datetime) -> dict[str, Any]:
    """Pure cryptographic binding for offline tests and trusted production."""
    import uuid
    if owner_oid not in module.EXACT_OWNER_OAUTH_SUBJECTS:
        raise IssuerActivationDenied("A0_SIGNED_OWNER_NOT_AUTHORIZED")
    scope = action_scope_sha256(policy)
    manifest = digest(json.dumps(dict(policy), sort_keys=True,
                                 separators=(",", ":")).encode())
    proof = module.issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid.uuid4().hex,
        release_id="release-" + policy["source_sha"][:16],
        candidate_sha=policy["source_sha"],
        rollback_sha=policy["source_sha"],
        scope_sha256=scope,
        manifest_sha256=manifest,
        freeze_sha256=policy["freeze_sha256"],
        verified_tenant_id=module.TID,
        verified_owner_oid=owner_oid,
        verified_principal=module.EXACT_OWNER_OAUTH_SUBJECTS[owner_oid],
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=at,
        private_key=signer,
    )
    module.verify_exact_owner_release(
        proof, public_key=trust,
        expected_candidate_sha=policy["source_sha"],
        expected_rollback_sha=policy["source_sha"],
        expected_release_id="release-" + policy["source_sha"][:16],
        expected_scope_sha256=scope,
        expected_manifest_sha256=manifest,
        expected_freeze_sha256=policy["freeze_sha256"], at=at,
    )
    return proof


def signed_exact_owner_approval(owner_oid: str,
                                policy: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse root-pinned Ed25519 Owner trust, never a caller-supplied key."""
    import uuid
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    # Read the *already installed* verifier; policy pins its exact bytes.
    read_root_file(OWNER_VERIFIER)
    spec = importlib.util.spec_from_file_location("a0_pinned_owner_verifier",
                                                   OWNER_VERIFIER)
    if spec is None or spec.loader is None:
        raise IssuerActivationDenied("A0_SIGNED_OWNER_VERIFIER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if owner_oid not in module.EXACT_OWNER_OAUTH_SUBJECTS:
        raise IssuerActivationDenied("A0_SIGNED_OWNER_NOT_AUTHORIZED")
    fd = os.open(SIGNER_KEY, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                or meta.st_uid != 1000 or stat.S_IMODE(meta.st_mode) != 0o400
                or meta.st_size != 32):
            raise IssuerActivationDenied("A0_EXISTING_SIGNER_UNTRUSTED")
        data = os.read(fd, 33)
    finally:
        os.close(fd)
    if len(data) != 32:
        raise IssuerActivationDenied("A0_EXISTING_SIGNER_SIZE_CHANGED")
    signer = Ed25519PrivateKey.from_private_bytes(data)
    trust = module.read_pinned_root_owner_public_key(
        PUBLIC_TRUST, require_root_owned=True,
    )
    if module.public_key_sha256(signer.public_key()) != module.public_key_sha256(trust):
        raise IssuerActivationDenied("A0_SIGNER_DOES_NOT_MATCH_ROOT_TRUST")
    return issue_bound_proof(
        owner_oid, policy, module=module, signer=signer,
        trust=trust, at=datetime.now(timezone.utc),
    )


def fresh_owner(helper: Any, policy: Mapping[str, Any]) -> str:
    service = "https://login.microsoftonline.com/" + helper.TENANT + "/oauth2/v2.0/"
    challenge = helper._form(service + "devicecode", {
        "client_id": helper.CLIENT_ID, "scope": helper.SCOPE,
    })
    if not all(isinstance(challenge.get(k), str)
               for k in ("device_code", "user_code", "verification_uri")):
        raise IssuerActivationDenied("A0_OWNER_OAUTH_UNAVAILABLE")
    lifetime = min(int(challenge.get("expires_in", 0)), 600)
    if lifetime < 60:
        raise IssuerActivationDenied("A0_OAUTH_CHALLENGE_TOO_SHORT")
    print("EXACT_ACTION=" + ACTION, flush=True)
    print("MCP_IMAGE=" + policy["mcp_image_sha256"], flush=True)
    print("ONLY_CHANGE=" + FLAG + "=true", flush=True)
    print("EXACT_SCOPE_SHA256=" + action_scope_sha256(policy), flush=True)
    print("PRODUCTION_FREEZE_AND_TICKET_CORE_UNCHANGED=true", flush=True)
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    deadline = time.monotonic() + lifetime
    interval = max(5, min(20, int(challenge.get("interval", 5))))
    while time.monotonic() < deadline:
        time.sleep(interval)
        token = helper._form(service + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": helper.CLIENT_ID,
            "device_code": challenge["device_code"],
        })
        if isinstance(token.get("access_token"), str):
            owner = helper.jwt_owner(token["access_token"])
            if input("Confirm exact action with APPROVE-EXACT-PMV4-A0-ISSUER-ONLY: ").strip() != "APPROVE-EXACT-PMV4-A0-ISSUER-ONLY":
                raise IssuerActivationDenied("A0_EXPLICIT_EXACT_ACTION_CONSENT_DENIED")
            return owner
        if token.get("error") == "slow_down":
            interval = min(20, interval + 5)
        elif token.get("error") != "authorization_pending":
            raise IssuerActivationDenied("A0_OWNER_OAUTH_REJECTED")
    raise IssuerActivationDenied("A0_OWNER_OAUTH_EXPIRED")


def execute() -> None:
    if (os.geteuid() != 0 or sys.flags.isolated != 1
            or Path(__file__).resolve(strict=True) != INSTALLED):
        raise IssuerActivationDenied("A0_ROOT_INSTALLED_ISOLATED_CODE_REQUIRED")
    policy = trusted_policy()
    owner_root = LEDGER.lstat()
    if (LEDGER.is_symlink() or owner_root.st_uid != 0
            or stat.S_IMODE(owner_root.st_mode) != 0o700):
        raise IssuerActivationDenied("A0_AUDIT_ROOT_UNTRUSTED")
    if list(LEDGER.glob(ACTION + ".*")):
        raise IssuerActivationDenied("A0_ONE_USE_ALREADY_CLAIMED")
    spec = importlib.util.spec_from_file_location("pmv4_trusted_owner", AUTH)
    if spec is None or spec.loader is None:
        raise IssuerActivationDenied("A0_TRUSTED_OWNER_HELPER_UNAVAILABLE")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.trusted_signer()
    initial = snapshot(policy)
    owner_oid = fresh_owner(helper, policy)
    helper.trusted_signer()
    signed_proof = signed_exact_owner_approval(owner_oid, policy)
    with old_release_lock():
        if trusted_policy() != policy:
            raise IssuerActivationDenied("A0_POLICY_CHANGED_DURING_OWNER_AUTH")
        verified = snapshot(policy)
        if (verified["mcp_id"] != initial["mcp_id"]
                or verified["runtime_id"] != initial["runtime_id"]):
            raise IssuerActivationDenied("A0_HOST_CHANGED_DURING_OWNER_AUTH")
        claim = LEDGER / (ACTION + ".attempt.json")
        atomic_record(claim, {
            "schema_version": "1.0", "action": ACTION, "source": policy["source_sha"],
            "owner_oid": owner_oid, "approved_script_sha256": policy["script_sha256"],
            "owner_signed_exact_action": signed_proof,
            "scope_sha256": action_scope_sha256(policy),
            "mcp_image": policy["mcp_image_sha256"],
            "freeze_sha256": policy["freeze_sha256"],
            "time": datetime.now(timezone.utc).isoformat(),
            "status": "exact_one_use_claimed_before_mutation",
        })
        command = [
            sys.executable, str(DEPLOYER),
            "--live", LIVE, "--image", policy["mcp_image_sha256"],
            "--rollback", ROLLBACK, "--source-revision", policy["source_sha"],
            "--health-url", "http://127.0.0.1:8000/healthz",
            "--health-attempts", "12", "--health-interval", "2",
            "--harden", "--set-env", FLAG + "=true",
        ]
        evidence = {"schema_version": "1.0", "action": ACTION, "result": "failed"}
        try:
            subprocess.run(command, check=True, timeout=200, stdout=subprocess.DEVNULL)
            after = docker(LIVE)
            verify_changed_only_one_flag(verified, after)
            if (docker(RUNTIME)["Id"] != verified["runtime_id"]
                    or digest(FREEZE.read_bytes()) != policy["freeze_sha256"]
                    or digest(HOLD.read_bytes()) != policy["promotion_hold_sha256"]):
                raise IssuerActivationDenied("A0_TICKET_CORE_OR_FREEZE_CHANGED")
            evidence.update({"result": "verified", "new_mcp_id": after["Id"]})
        except Exception:
            try:
                old = docker(ROLLBACK)
                if old["Id"] != verified["mcp_id"]:
                    raise IssuerActivationDenied("A0_ROLLBACK_CONTAINER_NOT_PINNED")
                subprocess.run(["docker", "rm", "-f", LIVE], check=True, timeout=45,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["docker", "rename", ROLLBACK, LIVE], check=True, timeout=30,
                               stdout=subprocess.DEVNULL)
                subprocess.run(["docker", "start", LIVE], check=True, timeout=45,
                               stdout=subprocess.DEVNULL)
                evidence["rolled_back"] = docker(LIVE)["Id"] == verified["mcp_id"]
            except Exception:
                evidence["rolled_back"] = False
            raise
        finally:
            evidence["time"] = datetime.now(timezone.utc).isoformat()
            atomic_record(LEDGER / (ACTION + ".result.json"), evidence)
    print("PMV4_A0_ISSUER_SAME_IMAGE=VERIFIED")
    print("TICKET_RUNTIME_CHANGED=false")
    print("PRODUCTION_FREEZE_CHANGED=false")


def main() -> int:
    parser = argparse.ArgumentParser()
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check-only", action="store_true")
    choice.add_argument("--execute", action="store_true")
    opts = parser.parse_args()
    try:
        if opts.check_only:
            # Unprivileged check-only reads only the already delegated status.
            root = Path("/var/lib/jason/openclaw/release-manager/protected-readback")
            control = json.loads((root / "production-control-state.json").read_bytes())
            state = control.get("circuit_breaker", {}).get("state")
            runtime, mcp = docker(RUNTIME), docker(LIVE)
            result = {
                "status": "observation_only", "breaker_state": state,
                "mcp_issuer": env_map(mcp).get(FLAG, "missing"),
                "runtime_healthy": runtime.get("State", {}).get("Health", {}).get("Status") == "healthy",
                "mcp_running": mcp.get("State", {}).get("Status") == "running",
                "production_mutation": False, "approval_issued": False,
            }
            print(json.dumps(result, sort_keys=True))
        else:
            execute()
    except (IssuerActivationDenied, OSError, ValueError, subprocess.SubprocessError,
            json.JSONDecodeError) as exc:
        print("PMV4_A0_ISSUER=DENIED " + type(exc).__name__ + ":" + str(exc)[:130],
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
