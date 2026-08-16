"""Provider-neutral contracts for governed evidence interpretation.

The reasoner may identify where an answer appears to exist, but it never supplies
an operational value. The verifier deterministically dereferences sanitized
provider evidence, rejects request/selector metadata, and fails closed when a
selection cannot be proven from the evidence bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

from .evidence_sanitization import REDACTED


AnswerType = Literal["direct", "derived", "unavailable"]


class EvidenceVerificationError(ValueError):
    """Raised when a reasoning plan cannot be proven from governed evidence."""


@dataclass(frozen=True, slots=True)
class EvidenceReasoningPlan:
    """Bounded model output describing evidence locations, never fact values."""

    answer_type: AnswerType
    evidence_paths: tuple[str, ...] = ()
    derivation_required: str | None = None

    def __post_init__(self) -> None:
        if self.answer_type not in {"direct", "derived", "unavailable"}:
            raise ValueError(f"unsupported answer_type: {self.answer_type}")
        if len(self.evidence_paths) > 64:
            raise ValueError("evidence selection exceeds the maximum path count")
        if len(set(self.evidence_paths)) != len(self.evidence_paths):
            raise ValueError("evidence paths must be unique")
        for path in self.evidence_paths:
            if not isinstance(path, str) or not path.startswith("/"):
                raise ValueError("evidence paths must be absolute JSON pointers")

        if self.answer_type == "unavailable":
            if self.evidence_paths or self.derivation_required is not None:
                raise ValueError(
                    "unavailable plans cannot claim evidence or derivations"
                )
            return

        if not self.evidence_paths:
            raise ValueError("supported answers require at least one evidence path")
        if self.answer_type == "direct" and self.derivation_required is not None:
            raise ValueError("direct answers cannot request a derivation")
        if self.answer_type == "derived" and not self.derivation_required:
            raise ValueError("derived answers require a named derivation")


class EvidenceReasoner(Protocol):
    """Select governed evidence locations for a human question.

    Implementations may use an AI model, but the return type intentionally has no
    field in which the model can assert the operational answer value.
    """

    def reason(
        self,
        *,
        question: str,
        evidence_catalog: Sequence[Mapping[str, Any]],
    ) -> EvidenceReasoningPlan:
        ...


@dataclass(frozen=True, slots=True)
class VerifiedEvidence:
    path: str
    value: Any
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class VerifiedEvidenceSelection:
    answer_type: AnswerType
    evidence: tuple[VerifiedEvidence, ...]
    derivation_required: str | None = None


class EvidenceVerifier:
    """Deterministically prove model-selected paths against sanitized evidence.

    Only data below configured evidence roots is dereferenceable. Orchestration
    metadata segments are never exposed as candidate facts and cannot be selected
    directly. Derived answers additionally require an explicitly approved named
    derivation.
    """

    _NON_FACT_SEGMENTS = frozenset(
        {
            "arguments",
            "evidence_contexts",
            "metadata",
            "prompt",
            "provenance",
            "request",
            "requested_facts",
            "resource_selector",
            "selector",
        }
    )

    def __init__(
        self,
        *,
        evidence_roots: Sequence[str] = ("/sections", "/references"),
        approved_derivations: Sequence[str] = (),
        max_selected_paths: int = 64,
    ) -> None:
        normalized = tuple(self._normalize_root(root) for root in evidence_roots)
        if not normalized:
            raise ValueError("at least one evidence root is required")
        if max_selected_paths < 1:
            raise ValueError("max_selected_paths must be positive")
        self._evidence_roots = normalized
        self._approved_derivations = frozenset(
            item.strip() for item in approved_derivations if item.strip()
        )
        self._max_selected_paths = max_selected_paths

    def verify(
        self,
        *,
        plan: EvidenceReasoningPlan,
        evidence_bundle: Mapping[str, Any],
    ) -> VerifiedEvidenceSelection:
        if plan.answer_type == "unavailable":
            return VerifiedEvidenceSelection(
                answer_type="unavailable",
                evidence=(),
                derivation_required=None,
            )

        if len(plan.evidence_paths) > self._max_selected_paths:
            raise EvidenceVerificationError(
                "reasoner selected more evidence paths than verifier permits"
            )

        if plan.answer_type == "derived":
            derivation = plan.derivation_required or ""
            if derivation not in self._approved_derivations:
                raise EvidenceVerificationError(
                    f"derivation is not approved: {derivation}"
                )

        verified: list[VerifiedEvidence] = []
        for path in plan.evidence_paths:
            normalized = self._normalize_pointer(path)
            self._require_evidence_root(normalized)
            self._require_fact_path(normalized)
            value = self._resolve_pointer(evidence_bundle, normalized)
            self._require_usable_value(value, normalized)
            provenance = self._nearest_provenance(evidence_bundle, normalized)
            verified.append(
                VerifiedEvidence(
                    path=normalized,
                    value=value,
                    provenance=provenance,
                )
            )

        return VerifiedEvidenceSelection(
            answer_type=plan.answer_type,
            evidence=tuple(verified),
            derivation_required=plan.derivation_required,
        )

    def catalog(
        self,
        evidence_bundle: Mapping[str, Any],
        *,
        include_containers: bool = False,
    ) -> tuple[Mapping[str, Any], ...]:
        """Create a model-readable path catalog without inventing semantics.

        Entries expose path, structural type, availability, and nearby provenance.
        Raw operational values are deliberately omitted: an AI reasoner chooses
        locations while deterministic verification performs dereferencing later.
        """

        entries: list[Mapping[str, Any]] = []
        for root in self._evidence_roots:
            try:
                value = self._resolve_pointer(evidence_bundle, root)
            except EvidenceVerificationError:
                continue
            self._walk_catalog(
                evidence_bundle=evidence_bundle,
                value=value,
                path=root,
                entries=entries,
                include_containers=include_containers,
            )
        return tuple(entries)

    def _walk_catalog(
        self,
        *,
        evidence_bundle: Mapping[str, Any],
        value: Any,
        path: str,
        entries: list[Mapping[str, Any]],
        include_containers: bool,
    ) -> None:
        if not self._is_fact_path(path):
            return

        if isinstance(value, Mapping):
            if include_containers:
                entries.append(
                    {
                        "path": path,
                        "type": "object",
                        "provenance": self._nearest_provenance(
                            evidence_bundle, path
                        ),
                    }
                )
            for key, child in value.items():
                child_path = f"{path}/{self._escape_pointer_token(str(key))}"
                self._walk_catalog(
                    evidence_bundle=evidence_bundle,
                    value=child,
                    path=child_path,
                    entries=entries,
                    include_containers=include_containers,
                )
            return

        if isinstance(value, (list, tuple)):
            if include_containers:
                entries.append(
                    {
                        "path": path,
                        "type": "array",
                        "length": len(value),
                        "provenance": self._nearest_provenance(
                            evidence_bundle, path
                        ),
                    }
                )
            for index, child in enumerate(value):
                self._walk_catalog(
                    evidence_bundle=evidence_bundle,
                    value=child,
                    path=f"{path}/{index}",
                    entries=entries,
                    include_containers=include_containers,
                )
            return

        entries.append(
            {
                "path": path,
                "type": self._scalar_type(value),
                "available": value not in (None, "", REDACTED),
                "provenance": self._nearest_provenance(evidence_bundle, path),
            }
        )

    def _require_evidence_root(self, path: str) -> None:
        for root in self._evidence_roots:
            if path == root or path.startswith(f"{root}/"):
                return
        raise EvidenceVerificationError(
            f"selected path is outside governed evidence roots: {path}"
        )

    def _require_fact_path(self, path: str) -> None:
        if not self._is_fact_path(path):
            raise EvidenceVerificationError(
                f"selected path is orchestration metadata, not evidence: {path}"
            )

    def _is_fact_path(self, path: str) -> bool:
        return not any(
            token.casefold() in self._NON_FACT_SEGMENTS
            for token in self._pointer_tokens(path)
        )

    @staticmethod
    def _require_usable_value(value: Any, path: str) -> None:
        if value is None or value == "" or value == REDACTED:
            raise EvidenceVerificationError(
                f"selected evidence is unavailable or redacted: {path}"
            )

    def _nearest_provenance(
        self,
        evidence_bundle: Mapping[str, Any],
        path: str,
    ) -> Mapping[str, Any]:
        tokens = self._pointer_tokens(path)
        for end in range(len(tokens), -1, -1):
            candidate_path = self._pointer_from_tokens(tokens[:end])
            try:
                candidate = self._resolve_pointer(
                    evidence_bundle,
                    candidate_path,
                )
            except EvidenceVerificationError:
                continue
            if not isinstance(candidate, Mapping):
                continue

            explicit = candidate.get("provenance")
            if isinstance(explicit, Mapping):
                return dict(explicit)

            metadata = {
                key: candidate[key]
                for key in (
                    "provider",
                    "source",
                    "method",
                    "path",
                    "status",
                    "collected_at",
                    "observed_at",
                )
                if key in candidate
                and not isinstance(candidate[key], (Mapping, list, tuple))
            }
            if metadata:
                return metadata

        return {}

    @classmethod
    def _resolve_pointer(cls, document: Any, pointer: str) -> Any:
        if pointer == "":
            return document

        current = document
        for token in cls._pointer_tokens(pointer):
            if isinstance(current, Mapping):
                if token not in current:
                    raise EvidenceVerificationError(
                        f"evidence path does not exist: {pointer}"
                    )
                current = current[token]
                continue

            if isinstance(current, (list, tuple)):
                if not token.isdigit():
                    raise EvidenceVerificationError(
                        f"array path token is not an index: {pointer}"
                    )
                index = int(token)
                if index >= len(current):
                    raise EvidenceVerificationError(
                        f"array index is outside evidence: {pointer}"
                    )
                current = current[index]
                continue

            raise EvidenceVerificationError(
                f"evidence path descends through a scalar: {pointer}"
            )

        return current

    @classmethod
    def _pointer_tokens(cls, pointer: str) -> tuple[str, ...]:
        normalized = cls._normalize_pointer(pointer)
        if normalized == "":
            return ()
        return tuple(
            cls._unescape_pointer_token(token)
            for token in normalized[1:].split("/")
        )

    @staticmethod
    def _normalize_pointer(pointer: str) -> str:
        if pointer == "":
            return ""
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise EvidenceVerificationError(
                "evidence path must be an absolute JSON pointer"
            )
        return pointer.rstrip("/") or "/"

    @classmethod
    def _normalize_root(cls, root: str) -> str:
        normalized = cls._normalize_pointer(root)
        if normalized in {"", "/"}:
            raise ValueError("the document root cannot be an evidence root")
        return normalized

    @staticmethod
    def _escape_pointer_token(token: str) -> str:
        return token.replace("~", "~0").replace("/", "~1")

    @staticmethod
    def _unescape_pointer_token(token: str) -> str:
        return token.replace("~1", "/").replace("~0", "~")

    @classmethod
    def _pointer_from_tokens(cls, tokens: Sequence[str]) -> str:
        if not tokens:
            return ""
        return "/" + "/".join(
            cls._escape_pointer_token(token) for token in tokens
        )

    @staticmethod
    def _scalar_type(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        return "string"
