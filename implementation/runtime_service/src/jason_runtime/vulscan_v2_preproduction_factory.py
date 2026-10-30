"""Explicit preproduction-only composition for VulScan V2 read sources.

No runtime auto-registration, new Teams sender, provider bypass, or standing
authority is performed here. Caller supplies currently authorized read ports.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .vulscan_governed_patch_source import VerifiedPatchTarget
from .vulscan_microsoft_public_source import (
    BoundedOfficialMicrosoftHTTP, GovernedMicrosoftKBReleaseReader,
)
from .vulscan_v2_preproduction_workflow import VulscanV2PreproductionWorkflow
from .vulscan_v2_site_inventory import (
    ApprovedDattoSiteInventory, collect_vulscan_v2_scoped_inventory,
)


def build_vulscan_v2_shadow_workflow(
    *, store: Any,
    authorized_site_inventory_read: Callable[[], ApprovedDattoSiteInventory],
    governed_read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    can_read_microsoft_public_docs: Callable[[], bool],
    authority_gate: Callable[[], bool] | None = None,
    microsoft_transport: BoundedOfficialMicrosoftHTTP | None = None,
) -> VulscanV2PreproductionWorkflow:
    """Create a dormant provider-verified workflow.

    Site scope and Datto capability invocations remain the caller's existing
    Central-Orchestrator-authorized adapters. This factory never manufactures
    a client mapping or a new provider grant.
    """
    transport = microsoft_transport or BoundedOfficialMicrosoftHTTP()
    reader = GovernedMicrosoftKBReleaseReader(
        transport=transport,
        can_read_official_public_docs=can_read_microsoft_public_docs,
    )
    return VulscanV2PreproductionWorkflow(
        store=store,
        inventory_reader=lambda: collect_vulscan_v2_scoped_inventory(
            site_inventory=authorized_site_inventory_read(),
            read=governed_read,
        ),
        patch_read=governed_read,
        microsoft_release_reader=reader,
        activation_verified=authority_gate,
    )
