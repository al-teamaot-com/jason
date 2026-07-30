from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import AudienceProfile, CommunicationDraft, CommunicationReview


@dataclass(frozen=True)
class TransformationRequest:
    draft: CommunicationDraft
    review: CommunicationReview
    profile: AudienceProfile
    preserve_facts: bool = True
    prohibit_new_commitments: bool = True


@dataclass(frozen=True)
class TransformationResult:
    subject: str | None
    body: str
    changes: tuple[str, ...]
    provider: str


class AudienceTransformer(Protocol):
    """Optional rewrite service. Output must be reviewed again before delivery."""

    def transform(self, request: TransformationRequest) -> TransformationResult: ...


class NoOpTransformer:
    provider = "deterministic_noop"

    def transform(self, request: TransformationRequest) -> TransformationResult:
        return TransformationResult(
            subject=request.draft.subject,
            body=request.draft.body,
            changes=(),
            provider=self.provider,
        )
