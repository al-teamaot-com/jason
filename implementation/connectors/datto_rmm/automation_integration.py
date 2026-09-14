from __future__ import annotations

from orchestrator.integration_broker import IntegrationManifest
from orchestrator.resource_capability_catalog import DATTO_RMM_PROVIDER

from .automation_manifest import build_datto_rmm_automation_resources


def build_datto_rmm_automation_read_manifest() -> IntegrationManifest:
    """Describe Datto's read-only automation evidence surface.

    This manifest intentionally contains no EXECUTE/WRITE operation. Component
    execution is a separate future governed capability and is not activated by
    registering this integration.
    """

    return IntegrationManifest(
        integration_id="datto_rmm_automation_reads",
        display_name="Datto RMM Automation Reads",
        manifest_version="1.0",
        provider_id=DATTO_RMM_PROVIDER,
        resources=build_datto_rmm_automation_resources(),
        metadata={
            "manifest_source": "integration",
            "authority": "descriptive_only",
            "read_only": "true",
            "documentation_url": (
                "https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm"
            ),
            "documentation_type": "html",
        },
    )
