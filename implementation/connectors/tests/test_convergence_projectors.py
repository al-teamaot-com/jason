import pytest

from connectors.convergence_projectors import (
    project_datto_rmm_device,
    project_it_glue_configuration,
)
from connectors.core.contracts import ConnectorResult
from connectors.resource_convergence import ResourceConvergenceError


def test_it_glue_configuration_projects_json_api_record() -> None:
    result = ConnectorResult(
        capability="it_glue.entity.get",
        provider="it_glue",
        data={
            "data": {
                "id": "321",
                "attributes": {
                    "name": "HOST-01",
                    "serial_number": "ABC123",
                },
            }
        },
    )

    evidence = project_it_glue_configuration(result, "org-1")

    assert evidence.provider == "it_glue"
    assert evidence.resource_type == "configuration"
    assert evidence.external_id == "321"
    assert evidence.organization_id == "org-1"
    assert evidence.attributes["name"] == "HOST-01"
    assert evidence.attributes["serial_number"] == "ABC123"


def test_datto_device_projects_single_search_result() -> None:
    result = ConnectorResult(
        capability="datto_rmm.device.search",
        provider="datto_rmm",
        data={
            "devices": [
                {
                    "uid": "device-1",
                    "hostname": "HOST-01",
                    "serialNumber": "ABC123",
                }
            ]
        },
    )

    evidence = project_datto_rmm_device(result, "org-1")

    assert evidence.provider == "datto_rmm"
    assert evidence.resource_type == "device"
    assert evidence.external_id == "device-1"
    assert evidence.attributes["hostname"] == "HOST-01"
    assert evidence.attributes["serial_number"] == "ABC123"


def test_datto_device_rejects_ambiguous_search_results() -> None:
    result = ConnectorResult(
        capability="datto_rmm.device.search",
        provider="datto_rmm",
        data={"devices": [{"uid": "a", "hostname": "A"}, {"uid": "b", "hostname": "B"}]},
    )

    with pytest.raises(ResourceConvergenceError, match="exactly one device candidate"):
        project_datto_rmm_device(result, "org-1")


def test_projectors_reject_wrong_provider_or_capability() -> None:
    with pytest.raises(ResourceConvergenceError, match="wrong provider"):
        project_it_glue_configuration(
            ConnectorResult(capability="it_glue.entity.get", provider="datto_rmm", data={}),
            "org-1",
        )

    with pytest.raises(ResourceConvergenceError, match="unsupported capability"):
        project_datto_rmm_device(
            ConnectorResult(capability="datto_rmm.alerts.list", provider="datto_rmm", data={}),
            "org-1",
        )


def test_projectors_require_stable_identifier_and_match_attributes() -> None:
    with pytest.raises(ResourceConvergenceError, match="stable external identifier"):
        project_it_glue_configuration(
            ConnectorResult(
                capability="it_glue.entity.get",
                provider="it_glue",
                data={"data": {"attributes": {"name": "HOST-01"}}},
            ),
            "org-1",
        )

    with pytest.raises(ResourceConvergenceError, match="no governed matching attributes"):
        project_datto_rmm_device(
            ConnectorResult(
                capability="datto_rmm.device.get",
                provider="datto_rmm",
                data={"device": {"uid": "device-1"}},
            ),
            "org-1",
        )
