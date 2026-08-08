#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from connectors.datto_rmm.connector import DattoRmmConnector  # noqa: E402
from connectors.it_glue.connector import ItGlueConnector  # noqa: E402
from connectors.resource_convergence import build_configuration_device_plan  # noqa: E402


def build_summary() -> dict[str, object]:
    plan = build_configuration_device_plan(
        organization_id="<organization-id>",
        configuration_id="<it-glue-configuration-id>",
        search_hint="<bounded-device-search-hint>",
    )
    return {
        "status": "credential_boundary_reached",
        "network_contacted": False,
        "secret_resolved": False,
        "provider_reads": [
            {
                "provider": read.query.provider,
                "resource_type": read.query.resource_type,
                "operation": read.query.operation.value,
                "capability": read.invocation.capability,
            }
            for read in plan.reads
        ],
        "required_logical_secrets": {
            "it_glue": {
                "logical_name": ItGlueConnector.logical_secret,
                "required_fields": ["api_key"],
            },
            "datto_rmm": {
                "logical_name": DattoRmmConnector.logical_secret,
                "required_fields": ["api_url", "api_key", "api_secret"],
                "runtime_material": ["access_token"],
                "persist_access_token": False,
            },
        },
        "next_live_validation": [
            "bind new read-only credentials through the Jason secret broker",
            "acquire the Datto bearer token at runtime without persisting it",
            "perform one bounded IT Glue configuration GET",
            "perform one bounded Datto RMM device search",
            "inspect only sanitized response shape and identity fields",
            "finalize provider response normalization without persisting raw provider payloads",
            "run the governed cross-provider match through the Central Orchestrator",
        ],
    }


def main() -> int:
    print(json.dumps(build_summary(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
