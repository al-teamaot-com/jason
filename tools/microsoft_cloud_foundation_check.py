#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from connectors.microsoft_graph.service_catalog import (  # noqa: E402
    MICROSOFT_ENDPOINTS,
    MICROSOFT_PERMISSION_PROFILES,
    MicrosoftOperationMode,
)


def build_summary() -> dict[str, object]:
    services = {
        service.value: {
            "provider": endpoint.provider_name,
            "base_url": endpoint.base_url,
            "api_version": endpoint.default_api_version,
            "modes": sorted(mode.value for mode in endpoint.supported_modes),
        }
        for service, endpoint in sorted(
            MICROSOFT_ENDPOINTS.items(), key=lambda item: item[0].value
        )
    }
    profiles = {
        name: {
            "services": sorted(service.value for service in profile.services),
            "maximum_mode": profile.maximum_mode.value,
            "permission_count": len(profile.application_permissions),
        }
        for name, profile in sorted(MICROSOFT_PERMISSION_PROFILES.items())
    }
    if any(
        profile.maximum_mode is not MicrosoftOperationMode.READ
        for profile in MICROSOFT_PERMISSION_PROFILES.values()
    ):
        raise RuntimeError("Initial Microsoft permission profiles must remain read-only.")
    return {
        "status": "approved",
        "network_contacted": False,
        "token_acquired": False,
        "services": services,
        "permission_profiles": profiles,
    }


def main() -> int:
    print(json.dumps(build_summary(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
