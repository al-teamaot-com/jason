#!/usr/bin/env python3
"""Fail-closed CCC installer approval preflight; performs no production writes."""
from __future__ import annotations
import argparse
import json
import os
import pwd
import re
import stat
from datetime import datetime
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")


def verify_install_review(*, revision: str, current_link: Path, review_file: Path | None) -> None:
    if not SHA.fullmatch(revision):
        raise ValueError("exact 40-character source revision required")
    current = current_link.resolve(strict=True).name if current_link.is_symlink() else None
    if current == revision and review_file is None:
        return
    if review_file is None:
        raise PermissionError("changing CCC checker requires an exact-revision owner review before production mutation")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(review_file, flags)
    try:
        info = os.fstat(fd)
        allowed_owners = {0, pwd.getpwnam("al").pw_uid}
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in allowed_owners or info.st_mode & 0o077:
            raise PermissionError("review evidence must be private and owned by an authorized local identity")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
            review = json.load(stream)
    finally:
        os.close(fd)
    if not isinstance(review, dict) or review.get("schema_version") != "1.0":
        raise ValueError("owner review schema invalid")
    if review.get("status") != "approved" or review.get("source_revision") != revision:
        raise PermissionError("owner review is not approved for the exact CCC revision")
    if review.get("recorded_by") != "person-al" or not str(review.get("reason") or "").strip():
        raise PermissionError("CCC material review requires the recorded owner and rationale")
    stamp = datetime.fromisoformat(str(review.get("recorded_at") or ""))
    if stamp.tzinfo is None:
        raise ValueError("owner review timestamp requires a time zone")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--current-link", type=Path, required=True)
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args()
    verify_install_review(revision=args.revision, current_link=args.current_link, review_file=args.review_file)
    print("CCC_INSTALL_OWNER_REVIEW_PREFLIGHT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
