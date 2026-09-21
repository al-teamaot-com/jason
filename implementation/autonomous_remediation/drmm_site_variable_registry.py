"""DRMM site-variable master registry and new-site convergence logic.

This module intentionally contains no provider transport. The central Jason
orchestrator supplies governed site inventory evidence and performs any approved
mutation. Provider variable values are never required by this module.

Two phases are deliberately separate:

1. Registry discovery: enumerate all authorized DRMM sites and reduce variable
   *names* plus configured/not-configured state into an AOT-wide master registry.
2. New-site convergence: compare one new site with the human-approved Standard
   subset and plan creation of missing variable names with blank values.

Discovery never promotes a variable to Standard. Existing variables are never
overwritten by this playbook.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Mapping, Sequence


PLAYBOOK_ID = "drmm_site_variable_master_registry"
PLAYBOOK_NAME = "Jason - DRMM Site Variable Master Registry"
PLAYBOOK_VERSION = "1.0.0"


class VariableDisposition(str, Enum):
    UNREVIEWED = "unreviewed"
    STANDARD = "standard"
    CLIENT_SPECIFIC = "client_specific"
    LEGACY = "legacy"
    DEPRECATED = "deprecated"


@dataclass(frozen=True, slots=True)
class VariableObservation:
    """Requester-safe provider observation. No variable value is permitted."""

    name: str
    configured: bool


@dataclass(frozen=True, slots=True)
class SiteInventory:
    site_uid: str
    site_name: str
    variables: tuple[VariableObservation, ...]


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    normalization_key: str
    canonical_name: str
    observed_names: tuple[str, ...]
    sites_present: int
    configured_sites: int
    coverage_percent: float
    candidate_standard: bool
    naming_collision: bool
    disposition: VariableDisposition = VariableDisposition.UNREVIEWED


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    generated_at: str
    total_sites: int
    scanned_sites: int
    failed_sites: tuple[str, ...]
    scan_complete: bool
    entries: tuple[RegistryEntry, ...]
    source_correlation_ids: tuple[str, ...] = ()

    def by_key(self) -> Mapping[str, RegistryEntry]:
        return {entry.normalization_key: entry for entry in self.entries}


@dataclass(frozen=True, slots=True)
class ApprovedStandardVariable:
    """Human-approved onboarding baseline item.

    Values are intentionally absent. The onboarding phase creates the name with a
    blank value; a later playbook may populate or validate it.
    """

    name: str
    masked: bool = True
    required: bool = True
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class ConvergenceAction:
    operation: str
    name: str
    value: str = ""
    masked: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ConvergencePlan:
    site_uid: str
    existing_standard_names: tuple[str, ...]
    create_actions: tuple[ConvergenceAction, ...]
    conflicts: tuple[str, ...]
    blocked: bool
    block_reasons: tuple[str, ...] = ()


class RegistryScanIncompleteError(RuntimeError):
    pass


def normalize_variable_name(name: str) -> str:
    """Analysis-only normalization.

    The normalized key is used to detect case/whitespace variants. It is never
    used to silently rename or merge provider objects.
    """

    return " ".join(str(name).strip().split()).casefold()


def _choose_canonical_name(name_counts: Mapping[str, int]) -> str:
    """Choose a deterministic display spelling without changing provider state."""

    return sorted(
        name_counts,
        key=lambda name: (-name_counts[name], name.casefold(), name),
    )[0]


def build_master_registry(
    inventories: Iterable[SiteInventory],
    *,
    total_site_count: int | None = None,
    failed_sites: Sequence[str] = (),
    source_correlation_ids: Sequence[str] = (),
    candidate_coverage_percent: float = 70.0,
    generated_at: datetime | None = None,
) -> RegistrySnapshot:
    """Reduce site inventories into a value-free master registry.

    A high coverage entry is merely marked candidate_standard. Human governance
    must explicitly classify it as Standard before onboarding may create it.
    """

    sites = tuple(inventories)
    total = total_site_count if total_site_count is not None else len(sites) + len(failed_sites)
    if total < len(sites):
        raise ValueError("total_site_count cannot be smaller than scanned inventory count")

    aggregates: dict[str, dict[str, object]] = {}

    for site in sites:
        seen_on_site: set[str] = set()
        for variable in site.variables:
            display_name = str(variable.name).strip()
            if not display_name:
                continue
            key = normalize_variable_name(display_name)
            if not key:
                continue

            item = aggregates.setdefault(
                key,
                {
                    "names": {},
                    "sites_present": 0,
                    "configured_sites": 0,
                },
            )
            names = item["names"]
            assert isinstance(names, dict)
            names[display_name] = int(names.get(display_name, 0)) + 1

            # Provider data should not contain the same logical variable twice on
            # one site, but duplicate rows must not inflate coverage.
            if key in seen_on_site:
                continue
            seen_on_site.add(key)
            item["sites_present"] = int(item["sites_present"]) + 1
            if variable.configured:
                item["configured_sites"] = int(item["configured_sites"]) + 1

    entries: list[RegistryEntry] = []
    denominator = total if total > 0 else 1

    for key, item in aggregates.items():
        names = item["names"]
        assert isinstance(names, dict)
        canonical = _choose_canonical_name(names)
        observed = tuple(sorted(names, key=lambda value: (value.casefold(), value)))
        present = int(item["sites_present"])
        configured = int(item["configured_sites"])
        coverage = round((present / denominator) * 100.0, 1)

        entries.append(
            RegistryEntry(
                normalization_key=key,
                canonical_name=canonical,
                observed_names=observed,
                sites_present=present,
                configured_sites=configured,
                coverage_percent=coverage,
                candidate_standard=coverage >= candidate_coverage_percent,
                naming_collision=len(observed) > 1,
            )
        )

    entries.sort(key=lambda entry: (-entry.sites_present, entry.canonical_name.casefold()))

    stamp = generated_at or datetime.now(timezone.utc)
    failures = tuple(sorted({str(name).strip() for name in failed_sites if str(name).strip()}))

    return RegistrySnapshot(
        generated_at=stamp.isoformat(),
        total_sites=total,
        scanned_sites=len(sites),
        failed_sites=failures,
        scan_complete=(len(sites) == total and not failures),
        entries=tuple(entries),
        source_correlation_ids=tuple(source_correlation_ids),
    )


def classify_registry(
    snapshot: RegistrySnapshot,
    decisions: Mapping[str, VariableDisposition | str],
) -> RegistrySnapshot:
    """Apply human-governed classifications without altering discovery evidence."""

    normalized_decisions = {
        normalize_variable_name(name): (
            value if isinstance(value, VariableDisposition) else VariableDisposition(value)
        )
        for name, value in decisions.items()
    }

    updated = tuple(
        RegistryEntry(
            normalization_key=entry.normalization_key,
            canonical_name=entry.canonical_name,
            observed_names=entry.observed_names,
            sites_present=entry.sites_present,
            configured_sites=entry.configured_sites,
            coverage_percent=entry.coverage_percent,
            candidate_standard=entry.candidate_standard,
            naming_collision=entry.naming_collision,
            disposition=normalized_decisions.get(entry.normalization_key, entry.disposition),
        )
        for entry in snapshot.entries
    )

    return RegistrySnapshot(
        generated_at=snapshot.generated_at,
        total_sites=snapshot.total_sites,
        scanned_sites=snapshot.scanned_sites,
        failed_sites=snapshot.failed_sites,
        scan_complete=snapshot.scan_complete,
        entries=updated,
        source_correlation_ids=snapshot.source_correlation_ids,
    )


def plan_new_site_convergence(
    *,
    snapshot: RegistrySnapshot,
    site_uid: str,
    current_variables: Sequence[VariableObservation],
    approved_standards: Sequence[ApprovedStandardVariable],
) -> ConvergencePlan:
    """Plan creation of missing approved standard names for one new DRMM site."""

    site_uid = str(site_uid).strip()
    if not site_uid:
        raise ValueError("site_uid is required")

    if not snapshot.scan_complete:
        raise RegistryScanIncompleteError(
            "A complete all-site registry scan is required before new-site convergence."
        )

    registry = snapshot.by_key()
    current_by_key: dict[str, list[str]] = {}
    for item in current_variables:
        raw_name = str(item.name).strip()
        if not raw_name:
            continue
        current_by_key.setdefault(normalize_variable_name(raw_name), []).append(raw_name)

    existing: list[str] = []
    actions: list[ConvergenceAction] = []
    conflicts: list[str] = []
    block_reasons: list[str] = []

    for standard in approved_standards:
        exact_name = str(standard.name).strip()
        if not exact_name:
            conflicts.append("Approved Standard contains an empty variable name.")
            continue

        key = normalize_variable_name(exact_name)
        discovered = registry.get(key)
        if discovered is None:
            conflicts.append(
                f"{exact_name}: approved Standard is absent from the current master registry."
            )
            continue
        if discovered.naming_collision:
            conflicts.append(
                f"{exact_name}: naming variants exist: {', '.join(discovered.observed_names)}"
            )
            continue

        target_names = current_by_key.get(key, [])
        if target_names:
            if any(name == exact_name for name in target_names):
                existing.append(exact_name)
            else:
                conflicts.append(
                    f"{exact_name}: target site already contains a case/whitespace variant "
                    f"({', '.join(sorted(target_names))}); no duplicate will be created."
                )
            continue

        actions.append(
            ConvergenceAction(
                operation="management.site.variable.create",
                name=exact_name,
                value="",
                masked=standard.masked,
                reason=(
                    "Create approved AOT Standard DRMM site-variable name during client onboarding. "
                    "Value intentionally left blank for later population/validation."
                ),
            )
        )

    if conflicts:
        block_reasons.append("Registry or target-site naming conflicts require human review.")

    return ConvergencePlan(
        site_uid=site_uid,
        existing_standard_names=tuple(sorted(existing, key=str.casefold)),
        create_actions=tuple(sorted(actions, key=lambda action: action.name.casefold())),
        conflicts=tuple(conflicts),
        blocked=bool(block_reasons),
        block_reasons=tuple(block_reasons),
    )
