from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence


def test_display_version_is_exposed_only_under_os_windows_release_context():
    adapted = adapt_datto_device_semantic_evidence({
        "health": {"version": "Unhealthy - Local user changes detected"},
        "operatingSystem": {"displayVersion": "24H2"},
    })
    assert adapted["semantic_evidence"]["operating_system"]["windows_release"]["operating_system_display_version"] == "24H2"
    assert adapted["health"]["version"] == "Unhealthy - Local user changes detected"


def test_ambiguous_provider_keys_fail_closed_by_omission():
    adapted = adapt_datto_device_semantic_evidence({
        "a": {"displayVersion": "23H2"},
        "b": {"DisplayVersion": "24H2"},
    })
    assert "semantic_evidence" not in adapted


def test_processor_model_and_count_remain_distinct_semantic_fields():
    adapted = adapt_datto_device_semantic_evidence({
        "hardware": {
            "processorModel": "Intel Core i7-12700",
            "logicalProcessors": 20,
        }
    })
    processor = adapted["semantic_evidence"]["processor"]["hardware_inventory"]
    assert processor["processor_model"] == "Intel Core i7-12700"
    assert processor["logical_processor_count"] == 20
