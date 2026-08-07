from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.operations import resolve_operation


def test_business_search_capabilities_are_registered() -> None:
    expected = {
        "autotask.company.search",
        "autotask.contact.search",
        "autotask.configuration_item.search",
        "autotask.contract.search",
        "autotask.project.search",
        "autotask.ticket.search",
    }
    assert expected <= AutotaskConnector.capabilities


def test_business_search_operations_are_get_only() -> None:
    expected_paths = {
        "autotask.company.search": "/V1.0/Companies/query",
        "autotask.contact.search": "/V1.0/Contacts/query",
        "autotask.configuration_item.search": "/V1.0/ConfigurationItems/query",
        "autotask.contract.search": "/V1.0/Contracts/query",
        "autotask.project.search": "/V1.0/Projects/query",
        "autotask.ticket.search": "/V1.0/Tickets/query",
    }

    for capability, expected_path in expected_paths.items():
        method, path, params = resolve_operation(
            capability,
            {"search": '{"filter":[]}'},
        )
        assert method == "GET"
        assert path == expected_path
        assert params == {"search": '{"filter":[]}'}
