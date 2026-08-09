#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from connectors.datto_rmm.connector import DattoRmmConnector
from connectors.it_glue.connector import ItGlueConnector
from connectors.resource_convergence import build_configuration_device_plan


def build_summary() -> dict[str, object]:
    plan = build_configuration_device_plan(
        organization_id="<organization-id>",
        configuration_id="<it-glue-configuration-id>",
        search_hint="<bounded-device-search-hint>",
        candidate_limit=5,
    )
    return {
        "status": "live_provider_boundaries_verified",
        "network_contacted": False,
        "secret_resolved": False,
        "provider_live_read_verified": {
            "it_glue": True,
            "datto_rmm": True,
        },
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
                "runtime_authentication": "approle",
            },
            "datto_rmm": {
                "logical_name": DattoRmmConnector.logical_secret,
                "runtime_authentication": "approle",
                "persist_access_token": False,
            },
        },
        "candidate_limit": 5,
        "next_live_validation": [
            "select one controlled IT Glue configuration and bounded Datto search hint",
            "perform independent governed reads under one exact organization context",
            "normalize only approved identity attributes observed from provider responses",
            "create relationship evidence only when selected attributes agree",
            "do not promote evidence to canonical truth automatically",
        ],
    }


def main() -> int:
    print(json.dumps(build_summary(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
