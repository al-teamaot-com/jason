from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence


def test_datto_display_version_is_not_treated_as_windows_release_evidence():
    adapted = adapt_datto_device_semantic_evidence({
        "operatingSystem": "Microsoft Windows 11 Pro 10.0.26200",
        "cagVersion": "11965",
        "displayVersion": "4.4.11965.11965",
    })
    semantic = adapted.get("semantic_evidence", {})
    assert "operating_system" not in semantic
    assert adapted["operatingSystem"] == "Microsoft Windows 11 Pro 10.0.26200"
    assert adapted["displayVersion"] == "4.4.11965.11965"


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


def test_semantic_adapter_accepts_equivalent_duplicate_processor_aliases():
    from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence

    value = "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz"
    adapted = adapt_datto_device_semantic_evidence(
        {
            "processor": value,
            "inventory": {"cpuModel": value},
        }
    )

    assert adapted["semantic_evidence"]["processor"]["hardware_inventory"]["processor_model"] == value


def test_semantic_adapter_rejects_conflicting_duplicate_processor_aliases():
    from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence

    adapted = adapt_datto_device_semantic_evidence(
        {
            "processor": "CPU-A",
            "inventory": {"cpuModel": "CPU-B"},
        }
    )

    semantic = adapted.get("semantic_evidence", {})
    assert "processor" not in semantic

def test_datto_last_seen_is_exposed_as_endpoint_presence_evidence():
    value = "2026-08-19T16:42:00Z"

    adapted = adapt_datto_device_semantic_evidence(
        {
            "uid": "device-123",
            "hostname": "AOT-50107",
            "lastSeen": value,
        }
    )

    assert (
        adapted["semantic_evidence"]["endpoint"]["presence"]["endpoint_last_seen"]
        == value
    )


def test_datto_last_seen_is_not_manufactured_when_provider_does_not_return_it():
    adapted = adapt_datto_device_semantic_evidence(
        {
            "uid": "device-123",
            "hostname": "AOT-50107",
        }
    )

    semantic = adapted.get("semantic_evidence", {})
    assert "endpoint" not in semantic
