from __future__ import annotations

from datetime import datetime, timezone

import pytest

from autonomous_remediation.drmm_site_variable_registry import (
    ApprovedStandardVariable,
    RegistryScanIncompleteError,
    SiteInventory,
    VariableDisposition,
    VariableObservation,
    build_master_registry,
    classify_registry,
    plan_new_site_convergence,
)


def inventory(site_uid: str, site_name: str, rows: list[tuple[str, bool]]) -> SiteInventory:
    return SiteInventory(
        site_uid=site_uid,
        site_name=site_name,
        variables=tuple(VariableObservation(name=name, configured=configured) for name, configured in rows),
    )


def test_build_master_registry_tracks_coverage_without_values():
    snapshot = build_master_registry(
        [
            inventory("s1", "One", [("BackupKey", True), ("Duo_IntegrationKey", True)]),
            inventory("s2", "Two", [("backupkey", False)]),
            inventory("s3", "Three", [("BackupKey", True)]),
        ],
        total_site_count=3,
        generated_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
    )

    assert snapshot.scan_complete is True
    backup = snapshot.by_key()["backupkey"]
    assert backup.sites_present == 3
    assert backup.configured_sites == 2
    assert backup.coverage_percent == 100.0
    assert backup.candidate_standard is True
    assert backup.naming_collision is True
    assert backup.observed_names == ("BackupKey", "backupkey")


def test_discovery_does_not_auto_promote_standard():
    snapshot = build_master_registry(
        [inventory("s1", "One", [("BackupKey", True)])],
        total_site_count=1,
    )
    assert snapshot.by_key()["backupkey"].candidate_standard is True
    assert snapshot.by_key()["backupkey"].disposition == VariableDisposition.UNREVIEWED


def test_human_classification_sets_standard():
    snapshot = build_master_registry(
        [inventory("s1", "One", [("BackupKey", True)])],
        total_site_count=1,
    )
    approved = classify_registry(snapshot, {"BackupKey": "standard"})
    assert approved.by_key()["backupkey"].disposition == VariableDisposition.STANDARD


def test_convergence_creates_only_missing_approved_names_blank():
    snapshot = build_master_registry(
        [
            inventory("s1", "One", [("BackupKey", True), ("DuoKey", True)]),
            inventory("s2", "Two", [("BackupKey", True), ("DuoKey", True)]),
        ],
        total_site_count=2,
    )

    plan = plan_new_site_convergence(
        snapshot=snapshot,
        site_uid="new-site",
        current_variables=(VariableObservation(name="BackupKey", configured=True),),
        approved_standards=(
            ApprovedStandardVariable(name="BackupKey"),
            ApprovedStandardVariable(name="DuoKey"),
        ),
    )

    assert plan.blocked is False
    assert plan.existing_standard_names == ("BackupKey",)
    assert len(plan.create_actions) == 1
    action = plan.create_actions[0]
    assert action.name == "DuoKey"
    assert action.value == ""
    assert action.masked is True
    assert action.operation == "management.site.variable.create"


def test_convergence_never_overwrites_existing_value():
    snapshot = build_master_registry(
        [inventory("s1", "One", [("BackupKey", True)])],
        total_site_count=1,
    )
    plan = plan_new_site_convergence(
        snapshot=snapshot,
        site_uid="new-site",
        current_variables=(VariableObservation(name="BackupKey", configured=True),),
        approved_standards=(ApprovedStandardVariable(name="BackupKey"),),
    )
    assert plan.create_actions == ()
    assert plan.existing_standard_names == ("BackupKey",)


def test_convergence_blocks_case_variant_instead_of_duplicate_creation():
    snapshot = build_master_registry(
        [inventory("s1", "One", [("BackupKey", True)])],
        total_site_count=1,
    )
    plan = plan_new_site_convergence(
        snapshot=snapshot,
        site_uid="new-site",
        current_variables=(VariableObservation(name="backupkey", configured=True),),
        approved_standards=(ApprovedStandardVariable(name="BackupKey"),),
    )
    assert plan.blocked is True
    assert plan.create_actions == ()
    assert "case/whitespace variant" in plan.conflicts[0]


def test_convergence_requires_complete_all_site_scan():
    snapshot = build_master_registry(
        [inventory("s1", "One", [("BackupKey", True)])],
        total_site_count=2,
        failed_sites=("Two",),
    )
    with pytest.raises(RegistryScanIncompleteError):
        plan_new_site_convergence(
            snapshot=snapshot,
            site_uid="new-site",
            current_variables=(),
            approved_standards=(ApprovedStandardVariable(name="BackupKey"),),
        )
