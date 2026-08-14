from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


@dataclass(frozen=True, slots=True)
class QualifiedCanonicalFactResolution:
    """Outcome of bounded qualifier analysis."""

    status: str
    definition: "CanonicalFactDefinition | None" = None

    def __post_init__(self) -> None:
        if self.status not in {
            "not_applicable",
            "resolved",
            "ambiguous",
        }:
            raise ValueError(
                "qualified canonical fact status is invalid"
            )

        if (
            self.status == "resolved"
            and self.definition is None
        ):
            raise ValueError(
                "resolved qualified fact requires a definition"
            )

        if (
            self.status != "resolved"
            and self.definition is not None
        ):
            raise ValueError(
                "unresolved qualified fact may not carry a definition"
            )


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
    evidence_hints: tuple[str, ...] = ()


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

    def resolve_qualified_human_text(
        self,
        *,
        human_text: str,
        eligible_facts: Iterable[str],
    ) -> QualifiedCanonicalFactResolution:
        """Resolve one governed fact contrast or report ambiguity.

        The method operates only on governed canonical definitions
        supplied through ``eligible_facts``.

        Resolution requires a recognition phrase shared by multiple
        eligible facts plus discriminating language for exactly one
        candidate. A shared anchor without a discriminator is
        ambiguous. Multiple discriminators are also ambiguous.

        This permits contrasts such as LAN versus WAN IP without
        making generic IP wording authoritative.

        A conservative ``-ly`` variant is recognized for one-word
        discriminators so ``internal`` can recognize ``internally``
        and ``external`` can recognize ``externally``.
        """

        definitions: list[
            CanonicalFactDefinition
        ] = []

        for raw_fact in eligible_facts:
            definition = self.resolve(
                str(raw_fact)
            )

            if (
                definition is not None
                and definition not in definitions
            ):
                definitions.append(definition)

        if len(definitions) < 2:
            return QualifiedCanonicalFactResolution(
                status="not_applicable",
            )

        recognition: dict[
            CanonicalFactDefinition,
            set[str],
        ] = {}

        phrase_counts: dict[str, int] = {}

        for definition in definitions:
            phrases: set[str] = set()

            for raw in (
                definition.canonical_fact,
                *definition.aliases,
                *definition.evidence_hints,
            ):
                normalized = self.normalize_text(
                    raw
                )

                if normalized:
                    phrases.add(normalized)

            recognition[definition] = phrases

            for phrase in phrases:
                phrase_counts[phrase] = (
                    phrase_counts.get(
                        phrase,
                        0,
                    )
                    + 1
                )

        shared = {
            phrase
            for phrase, count
            in phrase_counts.items()
            if count > 1
        }

        normalized_text = self.normalize_text(
            human_text
        )

        shared_present = any(
            self._recognition_phrase_matches(
                normalized_text,
                phrase,
            )
            for phrase in shared
        )

        if not shared_present:
            return QualifiedCanonicalFactResolution(
                status="not_applicable",
            )

        matched: list[
            CanonicalFactDefinition
        ] = []

        for definition in definitions:
            discriminators = (
                recognition[definition]
                - shared
            )

            discriminator_present = any(
                self._recognition_phrase_matches(
                    normalized_text,
                    phrase,
                )
                for phrase in discriminators
            )

            if discriminator_present:
                matched.append(definition)

        if len(matched) == 1:
            return QualifiedCanonicalFactResolution(
                status="resolved",
                definition=matched[0],
            )

        return QualifiedCanonicalFactResolution(
            status="ambiguous",
        )

    @staticmethod
    def _recognition_phrase_matches(
        normalized_text: str,
        normalized_phrase: str,
    ) -> bool:
        text_tokens = normalized_text.split()
        phrase_tokens = normalized_phrase.split()

        if not phrase_tokens:
            return False

        width = len(phrase_tokens)

        for index in range(
            len(text_tokens) - width + 1
        ):
            if (
                text_tokens[
                    index:index + width
                ]
                == phrase_tokens
            ):
                return True

        if (
            width == 1
            and phrase_tokens[0].isalpha()
            and (
                phrase_tokens[0] + "ly"
                in text_tokens
            )
        ):
            return True

        return False

    def canonicalize_requested_facts(
        self,
        *,
        human_text: str,
        requested_facts: Iterable[str],
    ) -> tuple[str, ...]:
        """Normalize reasoner fragments using explicit governed concepts in human text.

        A language model may split one concept such as ``Windows Display Version``
        into ``display`` and ``version``. Explicit canonical aliases in the original
        human text outrank that fragmentation. This method never invents concepts that
        are absent from the human request.
        """
        normalized_text = self.normalize_text(human_text)
        explicit: list[tuple[int, CanonicalFactDefinition]] = []
        for alias, definition in self._aliases.items():
            if not alias or not normalized_text:
                continue
            pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
            if re.search(pattern, normalized_text):
                explicit.append((len(alias), definition))

        if explicit:
            explicit.sort(key=lambda item: item[0], reverse=True)
            best_len = explicit[0][0]
            best = {definition for length, definition in explicit if length == best_len}
            if len(best) == 1:
                definition = next(iter(best))
                requested_words = {
                    token
                    for fact in requested_facts
                    for token in self.normalize_text(str(fact)).split()
                }
                concept_words = set()
                for raw in (definition.canonical_fact, *definition.aliases):
                    concept_words.update(self.normalize_text(raw).split())
                if requested_words and requested_words.issubset(concept_words):
                    return (definition.canonical_fact,)

        return tuple(self.canonicalize(str(item)) for item in requested_facts)


DEFAULT_CANONICAL_FACT_VOCABULARY = CanonicalFactVocabulary(
    (
        CanonicalFactDefinition(
            canonical_fact="LAN IP address",
            aliases=(
                "lan ip",
                "lan ip address",
                "local ip",
                "local ip address",
                "private ip",
                "private ip address",
                "internal ip",
                "internal ip address",
            ),
            expected_shape="private_ip_address",
            evidence_hints=(
                "lan",
                "local",
                "private",
                "internal",
                "ip",
                "ip address",
            ),
        ),
        CanonicalFactDefinition(
            canonical_fact="WAN IP address",
            aliases=(
                "wan ip",
                "wan ip address",
                "public ip",
                "public ip address",
                "external ip",
                "external ip address",
                "internet ip",
            ),
            expected_shape="public_ip_address",
            evidence_hints=(
                "wan",
                "public",
                "external",
                "internet",
                "ip",
                "ip address",
            ),
        ),
        CanonicalFactDefinition(
            canonical_fact="last logged in user",
            aliases=(
                "last logged in user",
                "logged in user",
                "last login user",
                "last user",
                "last user logged in",
                "last user logged into",
                "last user logged on",
            ),
            expected_shape="descriptive_string",
            evidence_hints=(
                "last logged in user",
                "logged in user",
                "last user",
                "login user",
                "username",
            ),
        ),
        CanonicalFactDefinition(
            canonical_fact="motherboard model",
            aliases=(
                "motherboard",
                "motherboard model",
                "mainboard",
                "mainboard model",
                "baseboard",
                "baseboard model",
                "system board",
                "system board model",
            ),
            expected_shape="descriptive_string",
            evidence_hints=(
                "motherboard",
                "mainboard",
                "baseboard",
                "system board",
                "product",
            ),
        ),
        CanonicalFactDefinition(
            canonical_fact="printers",
            aliases=(
                "printer",
                "printers",
                "installed printers",
                "printer devices",
            ),
            expected_shape="collection",
            evidence_hints=(
                "printer",
                "printers",
                "print device",
            ),
        ),
        CanonicalFactDefinition(
            canonical_fact="free disk space",
            aliases=(
                "free disk space",
                "disk free space",
                "available disk space",
                "free space",
            ),
            expected_shape="capacity",
            evidence_hints=(
                "free disk space",
                "disk free space",
                "freespace",
                "available space",
            ),
        ),
        CanonicalFactDefinition(
            canonical_fact="open alerts",
            aliases=(
                "open alert",
                "open alerts",
                "active alerts",
                "unresolved alerts",
                "alerts open",
            ),
            expected_shape="collection",
            evidence_hints=(
                "open alerts",
                "active alerts",
                "unresolved alerts",
                "alerts open",
            ),
        ),
        CanonicalFactDefinition(
            canonical_fact="disk error evidence",
            aliases=(
                "disk error",
                "disk errors",
                "disk error evidence",
                "disk error history",
                "historical disk errors",
                "disk event errors",
            ),
            expected_shape="evidence",
            evidence_hints=(
                "disk error",
                "disk errors",
                "bad block",
                "event log",
                "disk",
            ),
        ),
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
            evidence_hints=("model", "name", "caption", "processor", "cpu"),
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
            evidence_hints=("logical processors", "logical processor count", "thread count", "threads"),
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
            evidence_hints=("total physical memory", "physical memory", "total memory", "memory", "ram"),
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
            evidence_hints=("displayversion", "display version", "releaseid", "release id"),
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
            evidence_hints=(
                "network adapter",
                "network interface",
                "interface",
                "nic",
                "nics",
            ),
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
                "video card",
                "video cards",
                "gpu",
            ),
            expected_shape="collection",
            evidence_hints=(
                "display adapter",
                "video board",
                "graphics",
                "gpu",
            ),
        ),
    )
)
