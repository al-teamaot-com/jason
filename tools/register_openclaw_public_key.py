#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key


def fingerprint(path: Path) -> str:
    key = load_pem_public_key(path.read_bytes())
    der = key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Register an OpenClaw public signing key for Jason")
    parser.add_argument("--registry", type=Path, default=Path("/var/lib/jason/openclaw/trusted-keys/registry.json"))
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--machine-identity", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--expected-fingerprint", required=True)
    args = parser.parse_args()

    actual = fingerprint(args.public_key)
    if actual != args.expected_fingerprint:
        print(json.dumps({"status":"fail","reason":"fingerprint_mismatch","actual_fingerprint":actual}, sort_keys=True))
        return 2

    args.registry.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "keys": []}
    if args.registry.exists():
        payload = json.loads(args.registry.read_text(encoding="utf-8"))
        if not isinstance(payload.get("keys"), list):
            raise ValueError("existing registry keys field is invalid")

    record = {
        "key_id": args.key_id,
        "machine_identity": args.machine_identity,
        "public_key_path": str(args.public_key),
        "sha256_fingerprint": actual,
        "status": "active",
    }
    keys = [item for item in payload["keys"] if item.get("key_id") != args.key_id]
    keys.append(record)
    payload = {"version": 1, "keys": sorted(keys, key=lambda item: item["key_id"])}
    args.registry.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.registry.chmod(0o600)

    print(json.dumps({
        "status": "pass",
        "action": "openclaw_public_key_registered",
        "key_id": args.key_id,
        "machine_identity": args.machine_identity,
        "fingerprint": actual,
        "registry": str(args.registry),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
