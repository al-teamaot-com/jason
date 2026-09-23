from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationOperation,
    OperationKind,
    ResourceDefinition,
    ResourceObservation,
    SelectorDefinition,
)


def build_datto_rmm_automation_resources() -> tuple[ResourceDefinition, ...]:
    """Return provider-neutral read resources needed around component execution.

    These resources are descriptive/read-only. They do not enable the Datto
    quick-job mutation surface and do not imply EXECUTE authority.
    """

    component = ResourceDefinition(
        resource_type="automation_component",
        description=(
            "Approved automation component metadata observed through an RMM "
            "provider before any execution decision."
        ),
        selectors=(
            SelectorDefinition(
                name="name",
                description=(
                    "Human-readable component name or grounded name fragment "
                    "used for discovery."
                ),
            ),
        ),
        operations=(
            IntegrationOperation(
                operation_id="automation.component.search",
                kind=OperationKind.SEARCH,
                capability_name="automation.component.search",
                description=(
                    "Search the governed component catalog without executing a "
                    "component."
                ),
                read_only=True,
                selector_names=("name",),
                collection_supported=True,
            ),
        ),
        observations=(
            ResourceObservation(
                name="identity",
                description=(
                    "Durable provider component identity retained internally "
                    "with human-readable component metadata."
                ),
            ),
            ResourceObservation(
                name="input_contract",
                description=(
                    "Non-secret component variable names and type metadata used "
                    "to validate a future governed proposal."
                ),
            ),
        ),
    )

    job = ResourceDefinition(
        resource_type="automation_job",
        description=(
            "Read-only automation job state and bounded output used "
            "to verify a previously created provider job."
        ),
        selectors=(
            SelectorDefinition(
                name="resource_id",
                description=(
                    "Verified durable automation job identity."
                ),
                verified_identity_required=True,
            ),
            SelectorDefinition(
                name="device_uid",
                description=(
                    "Verified durable endpoint identity associated "
                    "with the job."
                ),
                verified_identity_required=True,
            ),
            SelectorDefinition(
                name="component_uid",
                description=(
                    "Verified durable automation component identity."
                ),
                verified_identity_required=True,
            ),
            SelectorDefinition(
                name="stream",
                description=(
                    "Requested bounded output stream: stdout or stderr."
                ),
            ),
        ),
        operations=(
            IntegrationOperation(
                operation_id="automation.job.read",
                kind=OperationKind.READ,
                capability_name="automation.job.read",
                description=(
                    "Read current governed automation job status "
                    "without changing the job or endpoint."
                ),
                read_only=True,
                selector_names=("resource_id",),
            ),
            IntegrationOperation(
                operation_id="automation.job.output.read",
                kind=OperationKind.READ,
                capability_name="automation.job.output.read",
                description=(
                    "Read bounded StdOut or StdErr for one verified "
                    "job, endpoint, and component."
                ),
                read_only=True,
                selector_names=(
                    "resource_id",
                    "device_uid",
                    "component_uid",
                    "stream",
                ),
            ),
        ),
        observations=(
            ResourceObservation(
                name="status",
                description=(
                    "Provider-reported job state, name, and creation "
                    "time when available."
                ),
            ),
            ResourceObservation(
                name="output",
                description=(
                    "Bounded provider-reported StdOut or StdErr "
                    "filtered to the requested component identity."
                ),
            ),
        ),
        relationships=(
            "automation_job -> endpoint",
            "automation_job -> automation_component",
        ),
    )

    return (component, job)
