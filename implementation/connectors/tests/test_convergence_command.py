from connectors.convergence_command import OperationalConvergenceCommand, OperationalConvergenceRunner
from connectors.core.contracts import ConnectorRequest, ConnectorResult


class StubConnector:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.capabilities = frozenset(
            {"it_glue.entity.get"} if provider == "it_glue" else {"datto_rmm.device.search"}
        )
        self.requests: list[ConnectorRequest] = []

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        self.requests.append(request)
        if self.provider == "it_glue":
            return ConnectorResult(
                capability=request.context.capability,
                provider="it_glue",
                data={"data": {"id": "321", "attributes": {"serial_number": "ABC123"}}},
            )
        return ConnectorResult(
            capability=request.context.capability,
            provider="datto_rmm",
            data={"devices": [{"uid": "device-1", "serialNumber": "ABC123"}]},
        )


def test_operational_command_wires_datto_authority_to_documentation_evidence() -> None:
    it_glue = StubConnector("it_glue")
    datto = StubConnector("datto_rmm")
    runner = OperationalConvergenceRunner({"it_glue": it_glue, "datto_rmm": datto})

    observation = runner.run(
        OperationalConvergenceCommand(
            organization_id="org-1",
            principal_id="operator-1",
            correlation_id="corr-1",
            configuration_id="321",
            search_hint="ABC123",
            matched_attributes=("serial_number",),
        )
    )

    assert observation.managed_device_authority.device.external_id == "device-1"
    assert observation.managed_device_authority.authoritative_provider == "datto_rmm"
    assert observation.relationship_status == "corroborated"
    assert observation.evidence is not None
    assert observation.evidence.source.external_id == "device-1"
    assert observation.evidence.target.external_id == "321"
    assert observation.evidence.metadata == {"matched_attributes": "serial_number"}
    assert observation.evidence.confidence == 1.0
    assert it_glue.requests[0].context.organization_id == "org-1"
    assert datto.requests[0].context.organization_id == "org-1"
    assert it_glue.requests[0].context.mode == "observe"
    assert datto.requests[0].context.mode == "observe"


def test_operational_command_requires_both_governed_connectors() -> None:
    try:
        OperationalConvergenceRunner({"it_glue": StubConnector("it_glue")})
    except ValueError as exc:
        assert "datto_rmm" in str(exc)
    else:
        raise AssertionError("runner must fail closed when a required connector is missing")
