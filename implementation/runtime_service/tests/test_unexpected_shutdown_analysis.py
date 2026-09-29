from jason_runtime.unexpected_shutdown_analysis import (
    classify_site_scope,
    shutdown_character,
    site_event_id,
    storage_health_risk,
)


def test_single_physical_device_is_device_specific():
    assert classify_site_scope(
        affected_physical_devices=1,
        active_physical_devices=8,
        ambiguous_physical_devices=0,
    ) == "DEVICE_SPECIFIC"


def test_three_or_more_correlated_physical_devices_is_site_environmental():
    assert classify_site_scope(
        affected_physical_devices=6,
        active_physical_devices=8,
        ambiguous_physical_devices=0,
    ) == "SITE_ENVIRONMENTAL"


def test_two_of_two_small_site_is_site_correlated_but_not_full_environmental_assertion():
    assert classify_site_scope(
        affected_physical_devices=2,
        active_physical_devices=2,
        ambiguous_physical_devices=0,
    ) == "SITE_CORRELATED_SMALL_SITE"


def test_ambiguous_peer_evidence_fails_closed():
    assert classify_site_scope(
        affected_physical_devices=1,
        active_physical_devices=6,
        ambiguous_physical_devices=1,
    ) == "UNDETERMINED"


def test_site_event_id_is_stable_for_same_site_and_window():
    first = site_event_id("Site A", 1790416800000)
    second = site_event_id("site a", 1790416800000 + 5 * 60 * 1000)
    assert first == second


def test_storage_health_flags_event_and_reliability_damage():
    risk, reasons = storage_health_risk(
        events=[{"Id": 7}],
        whea_events=[],
        physical_disks=[{"HealthStatus": "Healthy", "OperationalStatus": "OK"}],
        reliability=[{"ReadErrorsTotal": 3, "WriteErrorsTotal": 0}],
        volumes=[{"HealthStatus": "Healthy", "OperationalStatus": "OK"}],
    )
    assert risk is True
    assert "storage event 7" in reasons
    assert "reliability read=3 write=0" in reasons


def test_clean_storage_evidence_has_no_risk():
    risk, reasons = storage_health_risk(
        events=[],
        whea_events=[],
        physical_disks=[{"HealthStatus": "Healthy", "OperationalStatus": "OK"}],
        reliability=[{"ReadErrorsTotal": 0, "WriteErrorsTotal": 0}],
        volumes=[{"HealthStatus": "Healthy", "OperationalStatus": "OK"}],
    )
    assert risk is False
    assert reasons == ()


def test_shutdown_character_prefers_unclean_evidence():
    assert shutdown_character([{"Id": 6008}, {"Id": 6006}]) == "ABRUPT_OR_UNCLEAN"
    assert shutdown_character([{"Id": 1074}]) == "CLEAN_OR_PLANNED"
    assert shutdown_character([]) == "UNDETERMINED"
