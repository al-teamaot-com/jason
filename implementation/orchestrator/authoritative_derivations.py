"""Approved deterministic derivations over already-verified evidence.

Derivations never retrieve provider data and never trust a model-supplied value.
They operate only on values dereferenced by :mod:`evidence_interpreter` plus
explicit authoritative reference evidence selected through the same verifier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .evidence_interpreter import (
    EvidenceVerificationError,
    VerifiedEvidenceSelection,
)


WINDOWS_RELEASE_FROM_BUILD = "windows_release_from_build"

_WINDOWS_BUILD = re.compile(r"\b10\.0\.(?P<build>\d{5})(?:\.\d+)?\b")
_WINDOWS_EDITION = re.compile(
    r"\bWindows\s+11\s+(?P<edition>.+?)\s+10\.0\.\d{5}(?:\.\d+)?\b",
    flags=re.IGNORECASE,
)


class AuthoritativeDerivationError(EvidenceVerificationError):
    """Raised when verified evidence cannot support an approved derivation."""


@dataclass(frozen=True, slots=True)
class DerivedEvidenceValue:
    derivation: str
    value: Any
    source_paths: tuple[str, ...]


def _build_family(value: Any) -> str | None:
    if isinstance(value, int):
        rendered = str(value)
        return rendered if len(rendered) == 5 else None
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if re.fullmatch(r"\d{5}", candidate):
        return candidate
    match = _WINDOWS_BUILD.search(candidate)
    return match.group("build") if match else None


def _edition(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _WINDOWS_EDITION.search(value.strip())
    if not match:
        return None
    return " ".join(match.group("edition").split())


def windows_release_from_build(
    selection: VerifiedEvidenceSelection,
) -> DerivedEvidenceValue:
    """Resolve a Windows 11 friendly release from authoritative reference evidence.

    The selected evidence must contain a provider-observed Windows build and an
    authoritative reference pair whose build family matches it.  The function
    contains no build-to-release table of its own; that mapping remains evidence.
    """

    if selection.answer_type != "derived":
        raise AuthoritativeDerivationError(
            "Windows release derivation requires a derived evidence selection"
        )
    if selection.derivation_required != WINDOWS_RELEASE_FROM_BUILD:
        raise AuthoritativeDerivationError(
            "verified selection does not request the Windows release derivation"
        )

    provider_candidates = [
        item
        for item in selection.evidence
        if item.path.startswith("/sections/")
    ]
    reference_candidates = [
        item
        for item in selection.evidence
        if item.path.startswith("/references/")
    ]

    observed: list[tuple[str, str, str | None]] = []
    for item in provider_candidates:
        build = _build_family(item.value)
        if build is not None:
            observed.append((item.path, build, _edition(item.value)))

    if not observed:
        raise AuthoritativeDerivationError(
            "verified provider evidence contains no Windows build family"
        )

    reference_builds: list[tuple[str, str]] = []
    releases: list[tuple[str, str]] = []
    for item in reference_candidates:
        build = _build_family(item.value)
        if build is not None:
            reference_builds.append((item.path, build))
        if isinstance(item.value, str) and re.fullmatch(
            r"\d{2}H[12]", item.value.strip(), flags=re.IGNORECASE
        ):
            releases.append((item.path, item.value.strip().upper()))

    if not reference_builds or not releases:
        raise AuthoritativeDerivationError(
            "authoritative reference evidence lacks build/release values"
        )

    for provider_path, provider_build, edition in observed:
        for reference_build_path, reference_build in reference_builds:
            if provider_build != reference_build:
                continue

            # Build and release must come from the same reference record. This
            # prevents a model from combining unrelated authoritative rows.
            reference_parent = reference_build_path.rsplit("/", 1)[0]
            matching_releases = [
                (path, release)
                for path, release in releases
                if path.rsplit("/", 1)[0] == reference_parent
            ]
            if len(matching_releases) != 1:
                continue

            release_path, release = matching_releases[0]
            friendly = f"Windows 11 {release}"
            if edition:
                friendly = f"Windows 11 {edition} {release}"

            return DerivedEvidenceValue(
                derivation=WINDOWS_RELEASE_FROM_BUILD,
                value=friendly,
                source_paths=(
                    provider_path,
                    reference_build_path,
                    release_path,
                ),
            )

    raise AuthoritativeDerivationError(
        "no authoritative Windows release reference matches the observed build"
    )


class AuthoritativeDerivationRegistry:
    """Small allowlisted registry for deterministic evidence derivations."""

    def __init__(
        self,
        derivations: Mapping[
            str, Callable[[VerifiedEvidenceSelection], DerivedEvidenceValue]
        ]
        | None = None,
    ) -> None:
        self._derivations = dict(
            derivations
            or {
                WINDOWS_RELEASE_FROM_BUILD: windows_release_from_build,
            }
        )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._derivations))

    def derive(
        self,
        selection: VerifiedEvidenceSelection,
    ) -> DerivedEvidenceValue:
        name = selection.derivation_required
        if not name or name not in self._derivations:
            raise AuthoritativeDerivationError(
                f"no approved derivation is registered for: {name or '<none>'}"
            )
        return self._derivations[name](selection)
