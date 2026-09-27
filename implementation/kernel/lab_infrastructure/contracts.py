from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping


class LabAssetState(str, Enum):
    DEFINED = "defined"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class LabNetworkMode(str, Enum):
    ISOLATED = "isolated"


@dataclass(frozen=True, slots=True)
class LabLimits:
    max_vcpus: int = 4
    max_memory_mib: int = 8192
    max_disk_gib: int = 96

    def __post_init__(self) -> None:
        if min(self.max_vcpus, self.max_memory_mib, self.max_disk_gib) < 1:
            raise ValueError("Lab resource limits must be positive.")


@dataclass(frozen=True, slots=True)
class LabHostReadiness:
    hostname: str
    bare_metal: bool
    hardware_virtualization: bool
    kvm_device: bool
    libvirt_available: bool
    qemu_available: bool
    ovmf_available: bool
    swtpm_available: bool
    free_memory_mib: int
    free_disk_gib: int
    reasons: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            self.bare_metal
            and self.hardware_virtualization
            and self.kvm_device
            and self.libvirt_available
            and self.qemu_available
            and self.ovmf_available
            and self.swtpm_available
            and not self.reasons
        )


@dataclass(frozen=True, slots=True)
class LabHostDefinition:
    host_id: str
    hostname: str
    lab_only: bool
    allowed_image_ids: frozenset[str]
    network_mode: LabNetworkMode
    limits: LabLimits = field(default_factory=LabLimits)

    def __post_init__(self) -> None:
        if not self.host_id.strip() or not self.hostname.strip():
            raise ValueError("Lab host identity must be non-empty.")
        if not self.lab_only:
            raise ValueError("Only lab-only hosts may be registered.")
        if self.network_mode is not LabNetworkMode.ISOLATED:
            raise ValueError("Lab networking must be isolated.")
        if not self.allowed_image_ids:
            raise ValueError("At least one approved image is required.")


@dataclass(frozen=True, slots=True)
class LabVmSpec:
    vm_id: str
    host_id: str
    image_id: str
    image_path: str
    vcpus: int
    memory_mib: int
    disk_gib: int
    secure_boot: bool = True
    tpm_required: bool = True
    unattended: bool = True
    network_mode: LabNetworkMode = LabNetworkMode.ISOLATED
    production_domain_join: bool = False
    client_data_allowed: bool = False
    baseline_snapshot_required: bool = True
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.vm_id.strip() or not self.host_id.strip():
            raise ValueError("VM and host identity must be non-empty.")
        if not self.image_id.strip() or not self.image_path.strip():
            raise ValueError("An approved image identity and path are required.")
        if min(self.vcpus, self.memory_mib, self.disk_gib) < 1:
            raise ValueError("VM resources must be positive.")
        if self.network_mode is not LabNetworkMode.ISOLATED:
            raise ValueError("Lab VMs must use isolated networking.")
        if self.production_domain_join:
            raise ValueError("Production domain joins are forbidden in the lab.")
        if self.client_data_allowed:
            raise ValueError("Client data is forbidden in the lab.")
        if not self.baseline_snapshot_required:
            raise ValueError("A baseline snapshot is mandatory.")
        if not self.secure_boot or not self.tpm_required:
            raise ValueError("Windows 11 lab VMs require Secure Boot and TPM.")
        if not Path(self.image_path).is_absolute():
            raise ValueError("image_path must be absolute.")


@dataclass(frozen=True, slots=True)
class LabVmRecord:
    spec: LabVmSpec
    state: LabAssetState
    baseline_snapshot: str | None = None
    provider_id: str | None = None
