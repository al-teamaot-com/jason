#!/usr/bin/env python3
"""Run the Datto component approval-policy migration with a scoped ambiguity fix.

The original migration intentionally fails when a replacement is ambiguous. In
server.py, ``decided_by=principal`` legitimately exists in both the dedicated
Autotask internal-note path and the generic governed-action path. This wrapper
scopes that one replacement to ``_governed_execute`` and leaves every other
fail-closed replacement check unchanged.

This script changes source/tests only through the imported migration. It makes
no provider calls, performs no deployment, and restarts no services.
"""

from __future__ import annotations

import apply_datto_component_approval_policy as migration


_ORIGINAL_REPLACE_ONCE = migration.replace_once
_SERVER_PATH = "implementation/mcp_service/src/jason_mcp/server.py"
_AMBIGUOUS_OLD = "                decided_by=principal,\n"
_AMBIGUOUS_NEW = "                decided_by=approval_decided_by,\n"


def _scoped_replace_once(path: str, old: str, new: str) -> None:
    if path != _SERVER_PATH or old != _AMBIGUOUS_OLD or new != _AMBIGUOUS_NEW:
        _ORIGINAL_REPLACE_ONCE(path, old, new)
        return

    content = migration.read(path)
    start_marker = "def _governed_execute(\n"
    end_marker = "\ndef create_autotask_internal_note(\n"

    start = content.find(start_marker)
    end = content.find(end_marker, start + 1)

    if start < 0 or end < 0 or end <= start:
        raise migration.MigrationError(
            f"{path}: could not isolate generic governed-action function"
        )

    prefix = content[:start]
    governed = content[start:end]
    suffix = content[end:]

    count = governed.count(old)
    if count != 1:
        raise migration.MigrationError(
            f"{path}: expected one governed-action approval writer, found {count}"
        )

    migration.write(path, prefix + governed.replace(old, new, 1) + suffix)


def main() -> int:
    migration.replace_once = _scoped_replace_once
    return migration.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except migration.MigrationError as exc:
        print(
            f"DATTO_APPROVAL_POLICY_MIGRATION=FAIL: {exc}",
            file=__import__("sys").stderr,
        )
        raise SystemExit(1)
