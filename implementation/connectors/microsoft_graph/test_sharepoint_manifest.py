from connectors.microsoft_graph.sharepoint_manifest import build_sharepoint_read_manifest


def test_sharepoint_manifest_is_reusable_and_read_only():
    manifest = build_sharepoint_read_manifest()
    assert manifest.integration_id == "microsoft_graph_sharepoint_reader"
    assert manifest.provider_id == "microsoft_graph"
    operations = [
        operation for resource in manifest.resources for operation in resource.operations
    ]
    assert {operation.operation_id for operation in operations} == {
        "knowledge.library.search",
        "knowledge.document.search",
        "knowledge.document.metadata.read",
        "knowledge.document.content.read",
    }
    assert all(operation.read_only for operation in operations)
    assert not any(operation.operation_id.endswith("write") for operation in operations)
    assert all("site_id" in operation.selector_names for operation in operations)
