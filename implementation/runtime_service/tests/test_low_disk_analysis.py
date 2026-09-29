from jason_runtime.low_disk_analysis import (
    ONE_GIB,
    artifact_bytes,
    choose_cleanup,
    recommendation,
    relevant_findings,
    storage_health_summary,
)


def test_choose_cleanup_prefers_larger_safe_target():
    kind, amount = choose_cleanup(
        sysmon=[{"Bytes": 4 * ONE_GIB}],
        sysmon_dependencies=[],
        software_distribution=[{"Bytes": 7 * ONE_GIB}],
        storage_health_risk=False,
    )
    assert kind == "software_distribution_backups"
    assert amount == 7 * ONE_GIB


def test_sysmon_is_not_safe_when_service_depends_on_it():
    kind, amount = choose_cleanup(
        sysmon=[{"Bytes": 20 * ONE_GIB}],
        sysmon_dependencies=[{"Name": "SysmonService", "State": "Running"}],
        software_distribution=[],
        storage_health_risk=False,
    )
    assert kind is None
    assert amount == 0
def test_storage_health_risk_disables_cleanup():
    risk, summary = storage_health_summary(
        [{"FriendlyName": "Disk", "HealthStatus": "Warning", "OperationalStatus": "OK"}],
        [],
        0,
    )
    assert risk is True
    assert "health=Warning" in summary
    kind, _amount = choose_cleanup(
        sysmon=[{"Bytes": 10 * ONE_GIB}],
        sysmon_dependencies=[],
        software_distribution=[],
        storage_health_risk=risk,
    )
    assert kind is None


def test_relevant_findings_are_ranked_and_bounded():
    findings = relevant_findings(
        top_folders=[
            {"FullName": r"C:\\Users", "Bytes": 80 * ONE_GIB},
            {"FullName": r"C:\\Windows", "Bytes": 35 * ONE_GIB},
        ],
        large_files=[
            {"FullName": r"C:\\Temp\\old.iso", "Length": 12 * ONE_GIB, "Extension": ".iso"},
        ],
        vss=[{"UsedSpace": 9 * ONE_GIB}],
        system_files=[{"FullName": r"C:\\hiberfil.sys", "Length": 8 * ONE_GIB}],
        sysmon=[],
        software_distribution=[],
        limit=3,
    )
    assert len(findings) == 3
    assert findings[0].startswith(r"C:\\Users")
    assert any("old.iso" in item for item in findings)
def test_capacity_recommendation_when_no_safe_waste_is_found():
    text = recommendation(
        alert_still_open=True,
        storage_health_risk=False,
        cleanup_kind=None,
        cleanup_bytes=0,
        artifact_bytes=0,
    )
    assert "larger capacity" in text


def test_large_artifacts_are_review_not_auto_delete():
    files = [
        {"FullName": r"C:\\Temp\\install.iso", "Length": 6 * ONE_GIB, "Extension": ".iso"},
        {"FullName": r"C:\\Users\\x\\mail.ost", "Length": 9 * ONE_GIB, "Extension": ".ost"},
    ]
    total = artifact_bytes(files)
    assert total == 15 * ONE_GIB
    text = recommendation(
        alert_still_open=True,
        storage_health_risk=False,
        cleanup_kind=None,
        cleanup_bytes=0,
        artifact_bytes=total,
    )
    assert "Confirm whether they are still required" in text
