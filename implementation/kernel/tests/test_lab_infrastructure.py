from __future__ import annotations

from dataclasses import replace

import pytest

from kernel.lab_infrastructure import (
    InMemoryLabAssetRegistry,
    LabAssetState,
    LabHostDefinition,
    LabHostReadiness,
    LabInfrastructureError,
    LabInfrastructureService,
    LabLimits,
    LabNetworkMode,
    LabVmSpec,
)


class FakeProvider:
    def __init__(self) -> None:
        self.states = {}
        self.snapshots = {}

    def create(self, spec: LabVmSpec) -> str:
        provider_id = f"provider:{spec.vm_id}"
        self.states[provider_id] = LabAssetState.STOPPED
        self.snapshots[provider_id] = set()
        return provider_id

    def start(self, provider_id: str) -> None:
        self.states[provider_id] = LabAssetState.RUNNING

    def stop(self, provider_id: str) -> None:
        self.states[provider_id] = LabAssetState.STOPPED

    def delete(self, provider_id: str) -> None:
        self.states.pop(provider_id)
        self.snapshots.pop(provider_id)

    def snapshot_create(self, provider_id: str, name: str) -> None:
        self.snapshots[provider_id].add(name)

    def snapshot_revert(self, provider_id: str, name: str) -> None:
        assert name in self.snapshots[provider_id]
        self.states[provider_id] = LabAssetState.STOPPED

    def snapshot_delete(self, provider_id: str, name: str) -> None:
        self.snapshots[provider_id].remove(name)

    def state(self, provider_id: str) -> LabAssetState:
        return self.states[provider_id]


def host() -> LabHostDefinition:
    return LabHostDefinition(
        host_id="lab-host-1",
        hostname="jason-lab",
        lab_only=True,
        allowed_image_ids=frozenset({"windows-11-pro-approved"}),
        network_mode=LabNetworkMode.ISOLATED,
        limits=LabLimits(max_vcpus=4, max_memory_mib=8192, max_disk_gib=96),
    )


def spec() -> LabVmSpec:
    return LabVmSpec(
        vm_id="win11-regression-01",
        host_id="lab-host-1",
        image_id="windows-11-pro-approved",
        image_path="/var/lib/jason-lab/images/windows-11-pro.iso",
        vcpus=2,
        memory_mib=4096,
        disk_gib=64,
    )


def ready() -> LabHostReadiness:
    return LabHostReadiness(
        hostname="jason-lab",
        bare_metal=True,
        hardware_virtualization=True,
        kvm_device=True,
        libvirt_available=True,
        qemu_available=True,
        ovmf_available=True,
        swtpm_available=True,
        free_memory_mib=16384,
        free_disk_gib=200,
    )


def service():
    provider = FakeProvider()
    svc = LabInfrastructureService(
        registry=InMemoryLabAssetRegistry(),
        provider=provider,
    )
    svc.register_host(host())
    return svc, provider


def test_full_lab_vm_lifecycle_and_baseline_reset() -> None:
    svc, provider = service()
    record = svc.create_vm(spec=spec(), readiness=ready())
    record = svc.start(record.spec.vm_id)
    assert record.state is LabAssetState.RUNNING
    record = svc.stop(record.spec.vm_id)
    record = svc.create_baseline(record.spec.vm_id)
    assert record.baseline_snapshot == "baseline"
    record = svc.reset_to_baseline(record.spec.vm_id)
    assert record.state is LabAssetState.STOPPED
    svc.delete(record.spec.vm_id)
    assert provider.states == {}


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("production_domain_join", True),
        ("client_data_allowed", True),
        ("baseline_snapshot_required", False),
        ("secure_boot", False),
        ("tpm_required", False),
    ],
)
def test_vm_spec_rejects_guardrail_violations(field_name: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(spec(), **{field_name: value})


def test_fails_closed_when_hardware_virtualization_is_unavailable() -> None:
    svc, _ = service()
    unavailable = replace(
        ready(),
        hardware_virtualization=False,
        kvm_device=False,
        reasons=("CPU virtualization is not exposed", "/dev/kvm is absent"),
    )
    with pytest.raises(LabInfrastructureError, match="not ready"):
        svc.create_vm(spec=spec(), readiness=unavailable)


def test_rejects_unapproved_image() -> None:
    svc, _ = service()
    with pytest.raises(LabInfrastructureError, match="not approved"):
        svc.create_vm(
            spec=replace(spec(), image_id="unknown-image"),
            readiness=ready(),
        )


def test_enforces_fixed_resource_limits() -> None:
    svc, _ = service()
    with pytest.raises(LabInfrastructureError, match="memory"):
        svc.create_vm(
            spec=replace(spec(), memory_mib=16384),
            readiness=ready(),
        )


def test_reset_requires_baseline_snapshot() -> None:
    svc, _ = service()
    record = svc.create_vm(spec=spec(), readiness=ready())
    with pytest.raises(LabInfrastructureError, match="baseline"):
        svc.reset_to_baseline(record.spec.vm_id)
