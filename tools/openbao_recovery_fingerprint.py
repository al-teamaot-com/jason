from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
from datetime import datetime, timezone
from typing import Any, Sequence
from urllib.request import urlopen


DEFAULT_INIT_FILE = Path("/opt/jason/bootstrap/secrets/openbao/init.json")
DEFAULT_HEALTH_URL = "http://127.0.0.1:8200/v1/sys/health"


class FingerprintError(RuntimeError):
    """Raised when non-secret recovery evidence cannot be collected safely."""


def _require_new_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FingerprintError(f"Output already exists: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _load_initialization_metadata(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FingerprintError(f"Initialization file was not found: {resolved}")

    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise FingerprintError(
            f"Initialization file permissions are too broad: {oct(mode)}"
        )

    raw = resolved.read_bytes()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FingerprintError("Initialization file is not valid JSON.") from exc

    shares = data.get("unseal_keys_b64")
    share_count = data.get("unseal_shares")
    threshold = data.get("unseal_threshold")

    if not isinstance(shares, list) or not shares:
        raise FingerprintError("Initialization file has no unseal share list.")
    if not all(isinstance(item, str) and item.strip() for item in shares):
        raise FingerprintError("Initialization file has an invalid unseal share entry.")
    if share_count != len(shares):
        raise FingerprintError("Declared share count does not match protected material.")
    if not isinstance(threshold, int) or threshold < 1 or threshold > share_count:
        raise FingerprintError("Initialization file has an invalid unseal threshold.")

    file_stat = resolved.stat()
    return {
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact_size_bytes": len(raw),
        "artifact_mode": f"{mode:03o}",
        "artifact_uid": file_stat.st_uid,
        "artifact_gid": file_stat.st_gid,
        "share_count": share_count,
        "threshold": threshold,
        "root_token_present": bool(data.get("root_token")),
        "protected_values_exposed": False,
    }


def _load_health_metadata(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read())
            status = response.status
    except Exception as exc:
        status = getattr(exc, "code", None)
        if status is None or not hasattr(exc, "read"):
            raise FingerprintError("OpenBao health endpoint could not be read.") from exc
        payload = json.loads(exc.read())

    return {
        "health_http_status": status,
        "initialized": bool(payload.get("initialized")),
        "sealed": bool(payload.get("sealed")),
        "standby": bool(payload.get("standby")),
        "version": payload.get("version"),
        "cluster_id": payload.get("cluster_id"),
        "cluster_name": payload.get("cluster_name"),
    }


def collect(init_file: Path, health_url: str) -> dict[str, Any]:
    metadata = _load_initialization_metadata(init_file)
    metadata.update(_load_health_metadata(health_url))
    metadata.update(
        {
            "schema_version": "1.0",
            "evidence_type": "openbao-recovery-fingerprint",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "host": socket.gethostname(),
            "source_path": str(init_file.expanduser().resolve()),
        }
    )
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect non-secret OpenBao recovery fingerprint evidence."
    )
    parser.add_argument("--init-file", type=Path, default=DEFAULT_INIT_FILE)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = _require_new_output(args.output)
        if args.check_only:
            print("APPROVED: Fingerprint collection configuration validated; no protected file read and no output written.")
            return 0
        evidence = collect(args.init_file, args.health_url)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(output)
    except Exception as exc:
        parser.exit(1, f"DENIED: {exc}\n")

    print("APPROVED: Non-secret OpenBao recovery fingerprint evidence collected.")
    print(f"Evidence: {output}")
    print(f"Artifact SHA-256: {evidence['artifact_sha256']}")
    print(f"Share design: {evidence['share_count']}-of-{evidence['threshold']}")
    print(f"OpenBao version: {evidence['version']}")
    print(f"Initialized: {str(evidence['initialized']).lower()}")
    print(f"Sealed: {str(evidence['sealed']).lower()}")
    print("No unseal share, token, password, or secret value was displayed or stored in evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
