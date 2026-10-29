#!/usr/bin/env python3
"""Generate a non-executing Autotask capability gap report from reviewed JSON inventories.

Inputs are locally supplied *approved evidence*, not authority or execution grants.
Format: {"provider_operations": [{"method":"POST","path":"/V1.0/Tickets",
"operation":"Create ticket"}], "technician_ui_operations": [...]}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from implementation.connectors.autotask.technician_capability_inventory import discover_gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    if not isinstance(inventory, dict):
        parser.error("inventory must be an object")
    provider = inventory.get("provider_operations", [])
    ui = inventory.get("technician_ui_operations", [])
    if not isinstance(provider, list) or not isinstance(ui, list):
        parser.error("operation collections must be arrays")
    report = {
        "schema_version": 1,
        "authority": "evidence_only_no_execution",
        "findings": discover_gaps(provider, technician_ui_operations=ui),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
