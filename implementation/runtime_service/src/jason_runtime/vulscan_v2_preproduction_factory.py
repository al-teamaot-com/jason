"""Explicit preproduction-only composition for VulScan V2 read sources.

No runtime auto-registration, new Teams sender, provider bypass, or standing
authority is performed here. Caller supplies currently authorized read ports.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping
from datetime import datetime, timezone

from .vulscan_governed_patch_source import VerifiedPatchTarget
from .vulscan_owner_disposition_evidence import VerifiedPatchReviewDisposition
from .vulscan_datto_review_evidence import (
    DattoRmmPatchReviewReader, VerifiedDattoPolicyManualReview,
)
from .vulscan_policy_kb_attribution import VerifiedPolicyKBAttribution
from .vulscan_microsoft_public_source import (
    BoundedOfficialMicrosoftHTTP, GovernedMicrosoftKBReleaseReader,
)
from .vulscan_v2_preproduction_workflow import VulscanV2PreproductionWorkflow
from .vulscan_v2_site_inventory import (
    ApprovedDattoSiteInventory, ApprovedDattoSiteScope,
    VerifiedDattoSitePatchCollection, collect_vulscan_v2_scoped_inventory,
)


def build_vulscan_v2_shadow_workflow(
    *, store: Any,
    authorized_site_inventory_read: Callable[[], ApprovedDattoSiteInventory],
    governed_read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    can_read_microsoft_public_docs: Callable[[], bool],
    governed_review_disposition_read: Callable[[VerifiedPatchTarget], VerifiedPatchReviewDisposition] | None = None,
    # The approved AOT source for review decisions is Datto RMM, NOT a new
    # Jason ledger. This source must attest the policy's complete Manual
    # approval table for the exact client/site/device/policy/KB.
    governed_datto_manual_policy_review_read: Callable[[VerifiedPatchTarget], VerifiedDattoPolicyManualReview] | None = None,
    governed_policy_attribution_read: Callable[[str, str, str, str], VerifiedPolicyKBAttribution] | None = None,
    # Explicit preproduction alternative using complete governed device and
    # patch reads; no implicit fallback on missing site patch capability.
    governed_device_site_patch_read: Callable[[ApprovedDattoSiteScope], VerifiedDattoSitePatchCollection] | None = None,
    authority_gate: Callable[[], bool] | None = None,
    microsoft_transport: BoundedOfficialMicrosoftHTTP | None = None,
    microsoft_source_clock: Callable[[], datetime] | None = None,
) -> VulscanV2PreproductionWorkflow:
    """Create a dormant provider-verified workflow.

    Site scope and Datto capability invocations remain the caller's existing
    Central-Orchestrator-authorized adapters. This factory never manufactures
    a client mapping or a new provider grant.
    """
    transport = microsoft_transport or BoundedOfficialMicrosoftHTTP()
    evidence_clock = microsoft_source_clock or (lambda: datetime.now(timezone.utc))
    if (governed_review_disposition_read is not None
            and governed_datto_manual_policy_review_read is not None):
        raise ValueError("competing review evidence sources cannot be mixed")
    # Datto is the source of truth. When no complete governed Manual approval
    # reader is available, leave the review port unset and fail before scans.
    review_reader = (
        DattoRmmPatchReviewReader(
            governed_read=governed_read,
            policy_manual_review_read=governed_datto_manual_policy_review_read,
            now=evidence_clock,
        ) if governed_datto_manual_policy_review_read is not None
        else governed_review_disposition_read
    )
    reader = GovernedMicrosoftKBReleaseReader(
        transport=transport,
        can_read_official_public_docs=can_read_microsoft_public_docs,
        current_time=evidence_clock,
    )
    return VulscanV2PreproductionWorkflow(
        store=store,
        inventory_reader=lambda: collect_vulscan_v2_scoped_inventory(
            site_inventory=authorized_site_inventory_read(),
            read=governed_read,
            policy_attribution_read=governed_policy_attribution_read,
            verified_device_site_patch_read=governed_device_site_patch_read,
            now=evidence_clock(),
        ),
        patch_read=governed_read,
        microsoft_release_reader=reader,
        review_disposition_read=review_reader,
        activation_verified=authority_gate,
    )
