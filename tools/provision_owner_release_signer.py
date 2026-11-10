#!/usr/bin/env python3
"""One-time root-authorized Owner release signer provisioning; no deployment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pwd
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HOST_DIR = Path("/etc/jason/owner-release")
PRIVATE_NAME = "service-ed25519.private"
PUBLIC_NAME = "verified-owner-public-key.json"
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
OWNER_SUBJECTS = [
    {"owner_oid": "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
     "owner_principal": "person-entra-bee80bdcffb04c50b453c09d4d411f5f"},
    {"owner_oid": "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
     "owner_principal": "person-entra-c848022de13b445784b0e2f5c00dcaf6"},
]


def canonical_public(private: Ed25519PrivateKey) -> tuple[dict, str]:
    public_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public_bytes).hexdigest()
    return {
        "schema_version": "1.0",
        "authorization": "authenticated_entra_owner_exact_release",
        "organization_id": "aot",
        "tenant_id": TENANT,
        "authorized_owner_subjects": OWNER_SUBJECTS,
        "public_key_base64": base64.b64encode(public_bytes).decode("ascii"),
        "public_key_sha256": fingerprint,
        "standing_authority": False,
    }, fingerprint


def private_bytes(private: Ed25519PrivateKey) -> bytes:
    return private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def exclusive_file(path: Path, content: bytes, mode: int, uid: int, gid: int) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=False) as out:
            out.write(content)
            out.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def validate(dirpath: Path, uid: int, root_required: bool) -> str:
    priv = dirpath / PRIVATE_NAME
    pub = dirpath / PUBLIC_NAME
    meta = dirpath.lstat()
    private_meta = priv.lstat()
    public_meta = pub.lstat()
    if (dirpath.is_symlink() or not stat.S_ISDIR(meta.st_mode)
            or stat.S_IMODE(meta.st_mode) & 0o022
            or priv.is_symlink() or pub.is_symlink()
            or not stat.S_ISREG(private_meta.st_mode)
            or not stat.S_ISREG(public_meta.st_mode)
            or private_meta.st_uid != uid
            or stat.S_IMODE(private_meta.st_mode) != 0o400
            or stat.S_IMODE(public_meta.st_mode) & 0o022
            or (root_required and (meta.st_uid != 0 or public_meta.st_uid != 0))):
        raise PermissionError("OWNER_SIGNER_FILE_SECURITY_INVALID")
    raw = priv.read_bytes()
    if len(raw) != 32:
        raise ValueError("OWNER_SIGNER_PRIVATE_KEY_LENGTH_INVALID")
    private = Ed25519PrivateKey.from_private_bytes(raw)
    expected, fingerprint = canonical_public(private)
    if json.loads(pub.read_text(encoding="utf-8")) != expected:
        raise ValueError("OWNER_SIGNER_TRUST_POLICY_MISMATCH")
    return fingerprint


def provision(dirpath: Path, uid: int, gid: int, root_required: bool) -> tuple[str, str]:
    if root_required and os.geteuid() != 0:
        raise PermissionError("OWNER_SIGNER_REQUIRES_INTERACTIVE_ROOT")
    if dirpath.is_symlink():
        raise PermissionError("OWNER_SIGNER_DIRECTORY_SYMLINK")
    if dirpath.exists():
        meta = dirpath.lstat()
        if not stat.S_ISDIR(meta.st_mode) or stat.S_IMODE(meta.st_mode) & 0o022:
            raise PermissionError("OWNER_SIGNER_DIRECTORY_UNSAFE")
        if root_required and meta.st_uid != 0:
            raise PermissionError("OWNER_SIGNER_DIRECTORY_NOT_ROOT_OWNED")
    else:
        dirpath.mkdir(mode=0o700, parents=False)
    priv = dirpath / PRIVATE_NAME
    pub = dirpath / PUBLIC_NAME
    if priv.exists() or pub.exists() or priv.is_symlink() or pub.is_symlink():
        if not (priv.exists() and pub.exists()):
            raise PermissionError("OWNER_SIGNER_INCOMPLETE_PRIOR_PROVISION")
        return "ALREADY_PROVISIONED", validate(dirpath, uid, root_required)
    private = Ed25519PrivateKey.generate()
    policy, fingerprint = canonical_public(private)
    payload = (json.dumps(policy, sort_keys=True, indent=2) + "\n").encode()
    exclusive_file(priv, private_bytes(private), 0o400, uid, gid)
    try:
        exclusive_file(pub, payload, 0o644, 0 if root_required else uid, 0 if root_required else gid)
        validate(dirpath, uid, root_required)
        receipt = {
            "schema_version": "1.0",
            "status": "provisioned",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "owner_signer_public_key_sha256": fingerprint,
            "action": "provision_exact_owner_oauth_release_signer_only",
            "private_key_exported": False,
            "production_services_modified": False,
            "standing_release_authority": False,
        }
        exclusive_file(dirpath / "provision-receipt.json",
                       (json.dumps(receipt, sort_keys=True) + "\n").encode(),
                       0o600, 0 if root_required else uid, 0 if root_required else gid)
    except Exception:
        if not pub.exists():
            priv.unlink()
        raise
    return "PROVISIONED", fingerprint


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--provision", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        with tempfile.TemporaryDirectory(prefix="jason-owner-signer-test-") as tmp:
            root = Path(tmp) / "owner-release"
            uid, gid = os.getuid(), os.getgid()
            result, fingerprint = provision(root, uid, gid, False)
            assert result == "PROVISIONED"
            result2, fingerprint2 = provision(root, uid, gid, False)
            assert result2 == "ALREADY_PROVISIONED" and fingerprint == fingerprint2
            assert json.loads((root / PUBLIC_NAME).read_text())["standing_authority"] is False
            print("OWNER_SIGNER_SELF_TEST=PASS")
        return
    al = pwd.getpwnam("al")
    result, fingerprint = provision(HOST_DIR, al.pw_uid, al.pw_gid, True)
    print("OWNER_SIGNER_PROVISION_STATUS=" + result)
    print("OWNER_SIGNER_PUBLIC_SHA256=" + fingerprint)
    print("ROOT_TRUST_POLICY_VERIFIED=PASS")
    print("PRODUCTION_SERVICES_CHANGED=NO")


if __name__ == "__main__":
    main()
