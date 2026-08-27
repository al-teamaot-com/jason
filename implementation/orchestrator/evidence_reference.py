"""Provider-neutral JSON Pointer catalog and dereference utilities for governed evidence.

These helpers are intentionally semantic-free. They expose existing sanitized evidence
structure without teaching Jason provider fields, canonical facts, or question mappings.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from .evidence_sanitization import REDACTED


_MAX_CATALOG_ENTRIES = 4000
_MAX_PREVIEW_CHARS = 240


def build_evidence_catalog(value: Any) -> tuple[Mapping[str, Any], ...]:
    entries: list[Mapping[str, Any]] = []

    def walk(current: Any, pointer: str) -> None:
        if len(entries) >= _MAX_CATALOG_ENTRIES:
            return
        if isinstance(current, Mapping):
            entries.append(
                {
                    "path": pointer or "/",
                    "type": "object",
                    "selectable": False,
                }
            )
            for raw_key, child in current.items():
                key = str(raw_key).replace("~", "~0").replace("/", "~1")
                walk(child, f"{pointer}/{key}")
            return
        if isinstance(current, (list, tuple)):
            entries.append(
                {
                    "path": pointer or "/",
                    "type": "array",
                    "length": len(current),
                    "selectable": bool(current),
                }
            )
            for index, child in enumerate(current):
                walk(child, f"{pointer}/{index}")
            return
        if current is None or current == "" or current == REDACTED:
            return
        preview: Any = current
        if isinstance(current, str):
            preview = " ".join(current.split())[:_MAX_PREVIEW_CHARS]
        entries.append(
            {
                "path": pointer or "/",
                "type": type(current).__name__,
                "preview": preview,
                "selectable": True,
            }
        )

    walk(value, "")
    return tuple(entries[:_MAX_CATALOG_ENTRIES])



def build_evidence_frontier(
    value: Any,
    *,
    roots: tuple[str, ...] = ("/",),
    max_entries: int = 48,
) -> tuple[Mapping[str, Any], ...]:
    """Expose one bounded structural level beneath one or more JSON Pointer roots.

    This is intentionally provider-neutral and semantic-free. It allows a bounded
    reasoner to navigate large governed evidence trees without receiving a flattened
    catalog containing thousands of paths or provider values at once.
    """
    if max_entries < 1 or max_entries > 256:
        raise ValueError("evidence frontier entry bound is invalid")

    entries: list[Mapping[str, Any]] = []

    def append_child(child: Any, pointer: str) -> None:
        if len(entries) >= max_entries:
            return

        if isinstance(child, Mapping):
            keys = [
                str(key)
                for key in list(child.keys())[:16]
            ]
            entries.append(
                {
                    "path": pointer,
                    "type": "object",
                    "selectable": False,
                    "expandable": bool(child),
                    "child_count": len(child),
                    "keys": keys,
                }
            )
            return

        if isinstance(child, (list, tuple)):
            entries.append(
                {
                    "path": pointer,
                    "type": "array",
                    "selectable": False,
                    "expandable": bool(child),
                    "length": len(child),
                }
            )
            return

        if child is None or child == "" or child == REDACTED:
            return

        preview: Any = child
        if isinstance(child, str):
            preview = " ".join(child.split())[:120]

        entries.append(
            {
                "path": pointer,
                "type": type(child).__name__,
                "preview": preview,
                "selectable": True,
                "expandable": False,
            }
        )

    for root in roots:
        if len(entries) >= max_entries:
            break

        current = value if root == "/" else resolve_evidence_pointer(
            value,
            root,
        )

        if isinstance(current, Mapping):
            for raw_key, child in current.items():
                key = (
                    str(raw_key)
                    .replace("~", "~0")
                    .replace("/", "~1")
                )
                pointer = (
                    f"/{key}"
                    if root == "/"
                    else f"{root}/{key}"
                )
                append_child(child, pointer)
                if len(entries) >= max_entries:
                    break
            continue

        if isinstance(current, (list, tuple)):
            for index, child in enumerate(current):
                pointer = (
                    f"/{index}"
                    if root == "/"
                    else f"{root}/{index}"
                )
                append_child(child, pointer)
                if len(entries) >= max_entries:
                    break
            continue

        append_child(current, root)

    return tuple(entries)


def selectable_evidence_paths(value: Any) -> tuple[str, ...]:
    return tuple(
        str(item["path"])
        for item in build_evidence_catalog(value)
        if item.get("selectable") is True
    )


def resolve_evidence_pointer(document: Any, pointer: str) -> Any:
    if pointer == "/":
        return document
    if not pointer.startswith("/"):
        raise ValueError("evidence pointer must be absolute")
    current = document
    for raw in pointer.split("/")[1:]:
        segment = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if segment not in current:
                raise LookupError("selected evidence pointer no longer exists")
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            try:
                index = int(segment)
            except ValueError as error:
                raise LookupError("selected evidence pointer has invalid index") from error
            if index < 0 or index >= len(current):
                raise LookupError("selected evidence pointer index is out of range")
            current = current[index]
        else:
            raise LookupError("selected evidence pointer traverses a scalar")
    return current


def render_evidence_value(value: Any, *, max_chars: int = 1600) -> str:
    if max_chars < 16:
        raise ValueError("max_chars must be at least 16")
    if isinstance(value, str):
        rendered = value.strip()
    elif value is True:
        rendered = "Yes"
    elif value is False:
        rendered = "No"
    elif value is None:
        rendered = "null"
    elif isinstance(value, (int, float)):
        rendered = str(value)
    else:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3] + "..."
