from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import stat
from typing import Sequence


LAUNCHER = """#!/bin/sh
exec /usr/bin/env python3 /opt/jason/lib/jason_secret.py \"$@\"
"""


def install(*, source: Path, library_path: Path, launcher_path: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError("jason-secret source file was not found.")
    library_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, library_path)
    library_path.chmod(0o755)
    launcher_path.write_text(LAUNCHER, encoding="utf-8")
    launcher_path.chmod(
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
        stat.S_IRGRP | stat.S_IXGRP |
        stat.S_IROTH | stat.S_IXOTH
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the canonical Jason secret wrapper.")
    parser.add_argument("--source", type=Path, default=Path("tools/jason_secret.py"))
    parser.add_argument("--library-path", type=Path, default=Path("/opt/jason/lib/jason_secret.py"))
    parser.add_argument("--launcher-path", type=Path, default=Path("/usr/local/bin/jason-secret"))
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_only:
        if not args.source.is_file():
            raise SystemExit("DENIED: jason-secret source file was not found.")
        print("APPROVED: Installation configuration validated; no files changed.")
        return 0
    install(source=args.source, library_path=args.library_path, launcher_path=args.launcher_path)
    print(f"APPROVED: Installed jason-secret at {args.launcher_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
