"""Persist conversation targets only after governed evidence resolves durable identity.

This module defines a small provider-independent resource-resolution envelope for
conversation continuity. It does not infer identity from names, model output, or the
human selector. A literal target becomes a conversation entity only when a successful
governed result reports one durable resource id and corroborates it with exactly one
matching resource record.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .contracts import OrchestrationResult, OrchestrationStatus
from .dynamic_conversation_kernel import (
    ConversationEntity,
    ConversationReferenceResolution,
)
from .information_need_intent import PlannedInformationNeed


# Provider-neutral structural resource-resolution contract. Existing endpoint provider
# output already uses these names; future providers may emit the same envelope without
# exposing provider-specific identity fields to the Conversation Kernel.
RESOLVED_RESOURCE_ID = "resolved_resource_id"
RESOURCE_MATCHES = "resource_matches"
RESOURCE_ID = "resource_id"


@dataclass(frozen=True, slots=True)
class VerifiedConversationResourceObservation:
    entity: ConversationEntity
    resolution: ConversationReferenceResolution
    active_kind: str


def observe_verified_resource(
    *,
    planned: PlannedInformationNeed,
    result: OrchestrationResult,
) -> VerifiedConversationResourceObservation | None:
    target = planned.need.target
    if target.source != "literal":
        return None
    if result.status is not OrchestrationStatus.SUCCEEDED:
        return None
    if result.capability_name != planned.capability.capability_name:
        raise RuntimeError(
            "resource observation result does not match planned governed capability"
        )

    data = result.output.get("data")
    if not isinstance(data, Mapping):
        return None

    resource_id = str(data.get(RESOLVED_RESOURCE_ID, "")).strip()
    if not resource_id:
        return None

    raw_matches = data.get(RESOURCE_MATCHES)
    if not isinstance(raw_matches, Sequence) or isinstance(raw_matches, (str, bytes)):
        raise RuntimeError(
            "resolved resource identity lacks corroborating resource matches"
        )
    matches = tuple(item for item in raw_matches if isinstance(item, Mapping))
    if len(matches) != 1 or len(matches) != len(raw_matches):
        raise RuntimeError(
            "resolved conversation resource must have exactly one corroborating match"
        )
    match_id = str(matches[0].get(RESOURCE_ID, "")).strip()
    if not match_id or match_id != resource_id:
        raise RuntimeError(
            "resolved resource identity is inconsistent with corroborating match"
        )

    kind = target.kind.strip()
    display_name = target.reference.strip()
    ref = _entity_ref(kind=kind, canonical_id=resource_id)
    entity = ConversationEntity(
        ref=ref,
        kind=kind,
        canonical_id=resource_id,
        display_name=display_name,
        provenance=f"governed resource resolution:{result.execution_id}",
    )
    resolution = ConversationReferenceResolution(
        mention=display_name,
        entity_ref=ref,
        basis="governed resource resolved to durable identity",
    )
    return VerifiedConversationResourceObservation(
        entity=entity,
        resolution=resolution,
        active_kind=kind,
    )


def _entity_ref(*, kind: str, canonical_id: str) -> str:
    digest = sha256(
        (kind.strip() + "\x00" + canonical_id.strip()).encode("utf-8")
    ).hexdigest()[:20]
    return f"resource-{kind.strip()}-{digest}"
