from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CanonicalFactDefinition:
    """Provider-neutral fact concept and its human recognition vocabulary.

    Aliases are recognition input only. The canonical fact is what passes through
    governed inquiry/planning/evidence contracts. Expected shape is descriptive
    contract metadata; provider evidence validation is applied in a later layer.
    """

    canonical_fact: str
    aliases: tuple[str, ...]
    expected_shape: str


class CanonicalFactVocabulary:
    """Normalize varied human fact wording to a small governed vocabulary."""

    def __init__(self, definitions: Iterable[CanonicalFactDefinition]) -> None:
        self._definitions = tuple(definitions)
        aliases: dict[str, CanonicalFactDefinition] = {}
        for definition in self._definitions:
            for raw in (definition.canonical_fact, *definition.aliases):
                normalized = self.normalize_text(raw)
                if not normalized:
                    continue
                existing = aliases.get(normalized)
                if existing is not None and existing != definition:
                    raise ValueError(
                        f"canonical fact alias is ambiguous: {raw!r}"
                    )
                aliases[normalized] = definition
        self._aliases = aliases

    @staticmethod
    def normalize_text(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())

    @property
    def definitions(self) -> tuple[CanonicalFactDefinition, ...]:
        return self._definitions

    def resolve(self, value: str) -> CanonicalFactDefinition | None:
        normalized = self.normalize_text(value)
        if not normalized:
            return None

        exact = self._aliases.get(normalized)
        if exact is not None:
            return exact

        # Bounded typo tolerance is deliberately conservative. It applies only to
        # one-token human fact labels and only when exactly one governed alias is a
        # very close match. Semantic ambiguity must continue through bounded
        # reasoning or fail closed rather than being guessed here.
        if " " in normalized or len(normalized) < 4:
            return None

        candidates: list[tuple[float, CanonicalFactDefinition]] = []
        for alias, definition in self._aliases.items():
            if " " in alias:
                continue
            score = SequenceMatcher(a=normalized, b=alias).ratio()
            if score >= 0.80:
                candidates.append((score, definition))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score = candidates[0][0]
        best = {
            item[1]
            for item in candidates
            if abs(item[0] - best_score) < 0.03
        }
        if len(best) != 1:
            return None
        return next(iter(best))

    def canonicalize(self, value: str) -> str:
        definition = self.resolve(value)
        return definition.canonical_fact if definition is not None else value.strip()


DEFAULT_CANONICAL_FACT_VOCABULARY = CanonicalFactVocabulary(
    (
        CanonicalFactDefinition(
            canonical_fact="processor model",
            aliases=(
                "processor",
                "cpu",
                "cpu model",
                "processor name",
                "cpu name",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="logical processor count",
            aliases=(
                "logical processors",
                "logical processor count",
                "cpu count",
                "processor count",
                "threads",
                "thread count",
            ),
            expected_shape="integer_count",
        ),
        CanonicalFactDefinition(
            canonical_fact="total memory",
            aliases=(
                "memory",
                "ram",
                "physical memory",
                "installed memory",
                "total ram",
                "memory total",
            ),
            expected_shape="capacity",
        ),
        CanonicalFactDefinition(
            canonical_fact="operating system display version",
            aliases=(
                "windows display version",
                "displayversion",
                "windows release version",
                "windows feature version",
                "os display version",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="operating system build",
            aliases=(
                "windows build",
                "os build",
                "operating system build number",
                "windows build number",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="operating system",
            aliases=(
                "os",
                "windows version",
                "operating system version",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="bios version",
            aliases=("bios", "bios version"),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="network adapters",
            aliases=("network adapter", "network adapters", "nic", "nics"),
            expected_shape="collection",
        ),
        CanonicalFactDefinition(
            canonical_fact="logical disks",
            aliases=("logical disk", "logical disks", "disk", "disks"),
            expected_shape="collection",
        ),
        CanonicalFactDefinition(
            canonical_fact="display adapters",
            aliases=(
                "display adapter",
                "display adapters",
                "video board",
                "video boards",
                "graphics adapter",
                "graphics adapters",
                "gpu",
            ),
            expected_shape="collection",
        ),
    )
)
