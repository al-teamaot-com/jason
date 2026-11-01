#!/usr/bin/env python3
"""Read-only Autotask technician capability coverage from reviewed JSON evidence.

The input can contain provider_operations, technician_ui_operations,
and entity_metadata (governed entityInformation results). The optional
--previous report shows changes in supported operations or API-user access.

No data fetch, provider request, credential access, execution or activation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from implementation.connectors.autotask.entity_feature_matrix import (
    diff_entity_metadata,
    project_entity_metadata,
)
from implementation.connectors.autotask.technician_capability_inventory import discover_gaps
from implementation.connectors.autotask.existing_ticket_workflows import (
    action_reuse_index,
    inventory_ticket_workflows,
)


def build_report(
    inventory: dict[str, Any],
    previous: dict[str, Any] | None = None,
    *,
    workflow_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(inventory, dict):
        raise ValueError("inventory must be an object")
    provider = inventory.get("provider_operations", [])
    ui = inventory.get("technician_ui_operations", [])
    metadata = inventory.get("entity_metadata", [])
    if not all(isinstance(x, list) for x in (provider, ui, metadata)):
        raise ValueError("inventory operation collections must be arrays")
    matrix = project_entity_metadata(metadata) if metadata else []
    declared_workflows = (
        inventory_ticket_workflows(workflow_registry)
        if workflow_registry is not None else []
    )
    report: dict[str, Any] = {
        "schema_version": 2,
        "authority": "evidence_only_no_execution",
        "findings": discover_gaps(provider, technician_ui_operations=ui),
        "entity_action_matrix": matrix,
        "source_registered_ticket_workflows": declared_workflows,
        "existing_ticket_action_reuse": action_reuse_index(declared_workflows),
        "workflow_registry_supplied": workflow_registry is not None,
        "note": "Source registration never proves owner promotion, provider permissions or execution authority.",
    }
    if previous is not None:
        if not isinstance(previous, dict):
            raise ValueError("prior report must be an object")
        older = previous.get("entity_action_matrix")
        if not isinstance(older, list):
            raise ValueError("prior report missing entity action matrix")
        # An absent current entity scan is not an authoritative revocation.
        if not metadata:
            raise ValueError("cannot compare without current entity evidence")
        report["entity_action_changes"] = diff_entity_metadata(older, matrix)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--workflow-registry", type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    previous = (
        json.loads(args.previous.read_text(encoding="utf-8"))
        if args.previous is not None else None
    )
    workflow_registry = (
        json.loads(args.workflow_registry.read_text(encoding="utf-8"))
        if args.workflow_registry is not None else None
    )
    rendered = json.dumps(
        build_report(inventory, previous, workflow_registry=workflow_registry),
        indent=2, sort_keys=True,
    ) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
