#!/usr/bin/env python3
"""One-time root-only provision of the reviewed non-Teams Owner release signer."""
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

PRIVATE_DIR = Path("/var/lib/jason/runtime-secrets/owner-release")
TRUST_DIR = Path("/etc/jason-owner-release")
PRIVATE_NAME = "private_key"
PUBLIC_NAME = "verified-owner-public-key.json"
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
SUBJECTS = [
    {"owner_oid": "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
     "owner_principal": "person-entra-bee80bdcffb04c50b453c09d4d411f5f"},
    {"owner_oid": "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
     "owner_principal": "person-entra-c848022de13b445784b0e2f5c00dcaf6"},
]


def policy_for(key: Ed25519PrivateKey) -> tuple[dict, str]:
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    digest = hashlib.sha256(pub).hexdigest()
    return {
        "schema_version": "1.0",
        "authorization": "authenticated_entra_owner_exact_release",
        "organization_id": "aot",
        "tenant_id": TENANT,
        "authorized_owner_subjects": SUBJECTS,
        "public_key_base64": base64.b64encode(pub).decode("ascii"),
        "public_key_sha256": digest,
        "standing_authority": False,
    }, digest


def save_exclusive(path: Path, value: bytes, mode: int, uid: int, gid: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(value)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def validate(private_dir: Path, trust_dir: Path, uid: int, root: bool) -> str:
    priv, pub = private_dir / PRIVATE_NAME, trust_dir / PUBLIC_NAME
    d_priv, d_pub = private_dir.lstat(), trust_dir.lstat()
    s_priv, s_pub = priv.lstat(), pub.lstat()
    if (any(x.is_symlink() for x in (private_dir, trust_dir, priv, pub))
            or any(not stat.S_ISDIR(x.st_mode) for x in (d_priv, d_pub))
            or any(x.st_mode & 0o022 for x in (d_priv, d_pub))
            or not stat.S_ISREG(s_priv.st_mode)
            or not stat.S_ISREG(s_pub.st_mode)
            or s_priv.st_uid != uid
            or stat.S_IMODE(s_priv.st_mode) != 0o400
            or stat.S_IMODE(s_pub.st_mode) & 0o022
            or (root and (d_priv.st_uid != 0 or d_pub.st_uid != 0
                          or s_pub.st_uid != 0))):
        raise PermissionError("OWNER_SIGNER_FILE_SECURITY_INVALID")
    raw = priv.read_bytes()
    if len(raw) != 32:
        raise ValueError("OWNER_SIGNER_PRIVATE_KEY_LENGTH_INVALID")
    expected, digest = policy_for(Ed25519PrivateKey.from_private_bytes(raw))
    if json.loads(pub.read_text(encoding="utf-8")) != expected:
        raise ValueError("OWNER_SIGNER_ROOT_TRUST_MISMATCH")
    return digest


def ensure_directory(directory: Path, mode: int, uid: int, gid: int) -> None:
    if directory.is_symlink():
        raise PermissionError("OWNER_SIGNER_DIRECTORY_SYMLINK")
    if directory.exists():
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
                or info.st_uid != uid):
            raise PermissionError("OWNER_SIGNER_DIRECTORY_UNSAFE")
    else:
        directory.mkdir(mode=mode)
        os.chown(directory, uid, gid)
        os.chmod(directory, mode)


def provision(private_dir: Path, trust_dir: Path, uid: int, gid: int,
              root: bool) -> tuple[str, str]:
    if root and os.geteuid() != 0:
        raise PermissionError("OWNER_SIGNER_ROOT_REQUIRED")
    if root:
        base = trust_dir.parent
        info = base.lstat()
        if (base.is_symlink() or info.st_uid != 0
                or not stat.S_ISDIR(info.st_mode)
                or info.st_mode & 0o022):
            raise PermissionError("OWNER_SIGNER_ETC_ROOT_DIRECTORY_UNSAFE")
    ensure_directory(private_dir, 0o750 if root else 0o700,
                     0 if root else uid, gid)
    ensure_directory(trust_dir, 0o755 if root else 0o700,
                     0 if root else uid, 0 if root else gid)
    priv, pub = private_dir / PRIVATE_NAME, trust_dir / PUBLIC_NAME
    if (priv.exists() or pub.exists() or priv.is_symlink()
            or pub.is_symlink()):
        if not (priv.exists() and pub.exists()):
            raise PermissionError("OWNER_SIGNER_INCOMPLETE_PREVIOUS_PROVISION")
        status = "ALREADY_PROVISIONED"
        digest = validate(private_dir, trust_dir, uid, root)
    else:
        key = Ed25519PrivateKey.generate()
        policy, digest = policy_for(key)
        secret = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        save_exclusive(priv, secret, 0o400, uid, gid)
        try:
            save_exclusive(pub,
                           (json.dumps(policy, sort_keys=True, indent=2) + "\n").encode(),
                           0o644, 0 if root else uid, 0 if root else gid)
            validate(private_dir, trust_dir, uid, root)
        except Exception:
            if not pub.exists():
                priv.unlink()
            raise
        status = "PROVISIONED"
    if root:
        receipt = trust_dir / "provision-receipt.json"
        if not receipt.exists():
            record = {
                "schema_version": "1.0",
                "status": "provisioned",
                "when_utc": datetime.now(timezone.utc).isoformat(),
                "owner_release_signer_public_sha256": digest,
                "private_key_exported": False,
                "standing_release_authority": False,
                "production_services_changed": False,
                "existing_etc_directory_unchanged": True,
            }
            save_exclusive(receipt,
                           (json.dumps(record, sort_keys=True) + "\n").encode(),
                           0o600, 0, 0)
    return status, digest


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--provision", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        with tempfile.TemporaryDirectory(prefix="jason-signer-selftest-") as tmp:
            parent = Path(tmp)
            priv = parent / "private"
            trust = parent / "trust"
            uid, gid = os.getuid(), os.getgid()
            first, h = provision(priv, trust, uid, gid, False)
            again, h2 = provision(priv, trust, uid, gid, False)
            assert first == "PROVISIONED" and again == "ALREADY_PROVISIONED"
            assert h == h2
            assert not json.loads((trust / PUBLIC_NAME).read_text())["standing_authority"]
            print("OWNER_SIGNER_SELF_TEST=PASS")
        return
    al = pwd.getpwnam("al")
    result, digest = provision(PRIVATE_DIR, TRUST_DIR, al.pw_uid, al.pw_gid, True)
    print("OWNER_SIGNER_STATUS=" + result)
    print("OWNER_SIGNER_PUBLIC_SHA256=" + digest)
    print("ROOT_TRUST_READBACK=PASS")
    print("PRODUCTION_SERVICES_CHANGED=NO")


if __name__ == "__main__":
    main()
