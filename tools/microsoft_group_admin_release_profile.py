#!/usr/bin/env python3
"""Read only exact source-bound Microsoft 365 group admin activation declaration."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ALLOWED = {
    "schema_version": "1.0",
    "service": "aot-microsoft-group-admin",
    "profile": "aot-group-admin-exact-pilot-v1",
    "client_id": "client-aot-internal",
    "tenant_id": "f7054323-d52b-4863-8c2f-1898f0b6077c",
}

# A complete, minimal OFF profile permits independent Project Jason core
# releases without accidentally activating this separately governed pilot.
# A future ON release must restore ALLOWED exactly and obtain new Owner
# authorization. Unknown/partial documents must still fail closed.
ALLOWED_OFF = {
    "schema_version": "1.0",
    "service": "aot-microsoft-group-admin",
    "profile": "off",
}


def read_profile(source: Path) -> str:
    if source.is_symlink() or not source.is_file():
        raise PermissionError("M365_RELEASE_PROFILE_NOT_REGULAR")
    doc = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise PermissionError("M365_RELEASE_PROFILE_NOT_APPROVED")
    if doc == ALLOWED_OFF:
        return ""
    if doc != ALLOWED:
        raise PermissionError("M365_RELEASE_PROFILE_NOT_APPROVED")
    return str(doc["profile"])


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    args=parser.parse_args()
    print(read_profile(args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
