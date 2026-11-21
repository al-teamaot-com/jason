"""Resolve a rollback feature profile from the exact LKG Git tree.

Never select the candidate policy or a host environment override for a
rollback. The deploy scripts independently bind the LKG image to the same SHA.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def resolve(repo: Path, revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("rollback revision must be an immutable SHA")
    check = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", revision + "^{commit}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if check.returncode:
        raise ValueError("rollback revision is not a locally verified Git commit")
    path = "config/aot-staff-internal-note-profile.json"
    found = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", revision + ":" + path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if found.returncode:
        # Historical releases that predate the policy have no grant.
        return ""
    content = subprocess.run(
        ["git", "-C", str(repo), "show", revision + ":" + path],
        text=True, capture_output=True, check=False,
    )
    if content.returncode:
        raise ValueError("cannot read verified rollback declaration")
    data = json.loads(content.stdout)
    if (not isinstance(data, dict) or set(data) != {"profile", "schema_version"}
            or data.get("schema_version") != "1.0"
            or data.get("profile") not in ("off", "internal-note-v1")):
        raise ValueError("unrecognized rollback staff-note declaration")
    return "" if data["profile"] == "off" else "internal-note-v1"


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("expected repository and exact revision")
        print(resolve(Path(sys.argv[1]), sys.argv[2]))
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print("DENIED: " + str(exc), file=sys.stderr)
        sys.exit(2)
