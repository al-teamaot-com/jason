from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from kernel.lab_infrastructure.contracts import (
    LabAssetState,
    LabHostDefinition,
    LabHostReadiness,
    LabVmRecord,
    LabVmSpec,
)


class LabProvider(Protocol):
    def create(self, spec: LabVmSpec) -> str: ...
    def start(self, provider_id: str) -> None: ...
    def stop(self, provider_id: str) -> None: ...
    def delete(self, provider_id: str) -> None: ...
    def snapshot_create(self, provider_id: str, name: str) -> None: ...
    def snapshot_revert(self, provider_id: str, name: str) -> None: ...
    def snapshot_delete(self, provider_id: str, name: str) -> None: ...
    def state(self, provider_id: str) -> LabAssetState: ...


class LabInfrastructureError(RuntimeError):
    pass


class InMemoryLabAssetRegistry:
    def __init__(self) -> None:
        self.hosts: dict[str, LabHostDefinition] = {}
        self.vms: dict[str, LabVmRecord] = {}

    def add_host(self, host: LabHostDefinition) -> None:
        if host.host_id in self.hosts:
            raise LabInfrastructureError("Lab host already registered.")
        self.hosts[host.host_id] = host


class LabInfrastructureService:
    def __init__(self, *, registry: InMemoryLabAssetRegistry, provider: LabProvider) -> None:
        self._registry = registry
        self._provider = provider

    def register_host(self, host: LabHostDefinition) -> None:
        self._registry.add_host(host)

    def create_vm(self, *, spec: LabVmSpec, readiness: LabHostReadiness) -> LabVmRecord:
        host = self._registry.hosts.get(spec.host_id)
        if host is None:
            raise LabInfrastructureError("Target host is not an approved lab host.")
        if readiness.hostname != host.hostname:
            raise LabInfrastructureError("Host readiness evidence does not match target host.")
        if not readiness.ready:
            reason = "; ".join(readiness.reasons) or "hypervisor prerequisites are incomplete"
            raise LabInfrastructureError(f"Lab host is not ready: {reason}.")
        if spec.image_id not in host.allowed_image_ids:
            raise LabInfrastructureError("Image is not approved for this lab host.")
        if spec.vcpus > host.limits.max_vcpus:
            raise LabInfrastructureError("Requested vCPU count exceeds lab limit.")
        if spec.memory_mib > host.limits.max_memory_mib:
            raise LabInfrastructureError("Requested memory exceeds lab limit.")
        if spec.disk_gib > host.limits.max_disk_gib:
            raise LabInfrastructureError("Requested disk exceeds lab limit.")
        if spec.vm_id in self._registry.vms:
            raise LabInfrastructureError("Lab VM already exists.")

        provider_id = self._provider.create(spec)
        record = LabVmRecord(spec=spec, state=LabAssetState.DEFINED, provider_id=provider_id)
        self._registry.vms[spec.vm_id] = record
        return record

    def start(self, vm_id: str) -> LabVmRecord:
        record = self._require_vm(vm_id)
        self._provider.start(self._provider_id(record))
        updated = replace(record, state=self._provider.state(self._provider_id(record)))
        self._registry.vms[vm_id] = updated
        return updated

    def stop(self, vm_id: str) -> LabVmRecord:
        record = self._require_vm(vm_id)
        self._provider.stop(self._provider_id(record))
        updated = replace(record, state=self._provider.state(self._provider_id(record)))
        self._registry.vms[vm_id] = updated
        return updated

    def create_baseline(self, vm_id: str, name: str = "baseline") -> LabVmRecord:
        record = self._require_vm(vm_id)
        self._provider.snapshot_create(self._provider_id(record), name)
        updated = replace(record, baseline_snapshot=name)
        self._registry.vms[vm_id] = updated
        return updated

    def reset_to_baseline(self, vm_id: str) -> LabVmRecord:
        record = self._require_vm(vm_id)
        if not record.baseline_snapshot:
            raise LabInfrastructureError("VM has no verified baseline snapshot.")
        self._provider.snapshot_revert(self._provider_id(record), record.baseline_snapshot)
        updated = replace(record, state=self._provider.state(self._provider_id(record)))
        self._registry.vms[vm_id] = updated
        return updated

    def delete(self, vm_id: str) -> None:
        record = self._require_vm(vm_id)
        self._provider.delete(self._provider_id(record))
        del self._registry.vms[vm_id]

    def _require_vm(self, vm_id: str) -> LabVmRecord:
        try:
            return self._registry.vms[vm_id]
        except KeyError as exc:
            raise LabInfrastructureError("Unknown lab VM.") from exc

    @staticmethod
    def _provider_id(record: LabVmRecord) -> str:
        if not record.provider_id:
            raise LabInfrastructureError("Lab VM has no provider identity.")
        return record.provider_id
