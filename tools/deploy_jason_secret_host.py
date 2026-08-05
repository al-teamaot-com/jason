from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Sequence


DEFAULT_MAPPINGS = {
    "jason.contract-test": {
        "path": "secret/data/jason/contract-test",
        "field": "value",
    }
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_private_file(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"Protected file permissions are too broad: {path}")


def install_non_secret_components(
    *,
    source: Path,
    library_path: Path,
    launcher_path: Path,
    mapping_path: Path,
    token_path: Path,
) -> dict[str, object]:
    if os.geteuid() != 0:
        raise PermissionError("Host installation must run as root.")
    if not source.is_file():
        raise FileNotFoundError("jason-secret source file was not found.")

    library_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(source, library_path)
    library_path.chmod(0o755)
    launcher_path.write_text(
        '#!/bin/sh\nexec /usr/bin/env python3 /opt/jason/lib/jason_secret.py "$@"\n',
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)

    if not mapping_path.exists():
        mapping_path.write_text(json.dumps(DEFAULT_MAPPINGS, indent=2) + "\n", encoding="utf-8")
    mapping_path.chmod(0o640)

    syntax = subprocess.run(
        ["/usr/bin/env", "python3", "-m", "py_compile", str(library_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if syntax.returncode != 0:
        raise RuntimeError("Installed jason-secret syntax validation failed.")

    return {
        "phase": "non_secret_components_installed",
        "library_path": str(library_path),
        "library_sha256": sha256(library_path),
        "launcher_path": str(launcher_path),
        "launcher_sha256": sha256(launcher_path),
        "mapping_path": str(mapping_path),
        "mapping_sha256": sha256(mapping_path),
        "token_path": str(token_path),
        "token_present": token_path.is_file(),
        "syntax_validation": "approved",
        "openbao_contacted": False,
        "secret_resolved": False,
    }


def deploy_authenticated(
    *,
    source: Path,
    library_path: Path,
    launcher_path: Path,
    mapping_path: Path,
    token_path: Path,
) -> dict[str, object]:
    evidence = install_non_secret_components(
        source=source,
        library_path=library_path,
        launcher_path=launcher_path,
        mapping_path=mapping_path,
        token_path=token_path,
    )
    if not token_path.is_file():
        raise FileNotFoundError("OpenBao authentication file was not found.")
    ensure_private_file(token_path)

    health = subprocess.run(
        [str(launcher_path), "--health"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={
            **os.environ,
            "JASON_SECRET_MAPPING_FILE": str(mapping_path),
            "JASON_OPENBAO_TOKEN_FILE": str(token_path),
        },
    )
    if health.returncode != 0 or health.stdout.strip() != "healthy":
        raise RuntimeError("jason-secret health validation failed.")

    evidence.update(
        {
            "phase": "authenticated_deployment_verified",
            "token_present": True,
            "health": "approved",
            "openbao_contacted": True,
        }
    )
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install and verify the canonical jason-secret wrapper on one host.")
    parser.add_argument("--source", type=Path, default=Path("tools/jason_secret.py"))
    parser.add_argument("--library-path", type=Path, default=Path("/opt/jason/lib/jason_secret.py"))
    parser.add_argument("--launcher-path", type=Path, default=Path("/usr/local/bin/jason-secret"))
    parser.add_argument("--mapping-path", type=Path, default=Path("/etc/jason/secret-mappings.json"))
    parser.add_argument("--token-path", type=Path, default=Path("/etc/jason/openbao.token"))
    parser.add_argument("--evidence-output", type=Path)
    parser.add_argument("--non-secret-install", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def write_evidence(path: Path, evidence: dict[str, object]) -> Path:
    output = path.expanduser().resolve()
    if output.exists():
        raise FileExistsError("Evidence output already exists.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return output


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_only:
        if not args.source.is_file():
            raise SystemExit("DENIED: jason-secret source file was not found.")
        print("APPROVED: Host installation configuration validated; no files changed.")
        return 0
    try:
        operation = install_non_secret_components if args.non_secret_install else deploy_authenticated
        evidence = operation(
            source=args.source,
            library_path=args.library_path,
            launcher_path=args.launcher_path,
            mapping_path=args.mapping_path,
            token_path=args.token_path,
        )
        if args.evidence_output:
            output = write_evidence(args.evidence_output, evidence)
            print(f"Evidence: {output}")
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc

    if args.non_secret_install:
        print("APPROVED: Non-secret jason-secret host components installed; authentication remains unconfigured.")
    else:
        print("APPROVED: jason-secret authenticated host deployment verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
