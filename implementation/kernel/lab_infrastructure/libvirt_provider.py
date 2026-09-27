from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol, Sequence

from kernel.lab_infrastructure.contracts import LabAssetState, LabVmSpec
from kernel.lab_infrastructure.service import LabInfrastructureError


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str]) -> str: ...


class SubprocessCommandRunner:
    def run(self, argv: Sequence[str]) -> str:
        try:
            completed = subprocess.run(
                list(argv),
                check=True,
                capture_output=True,
                text=True,
                shell=False,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise LabInfrastructureError(
                f"Lab hypervisor command failed: {stderr or exc.returncode}"
            ) from exc
        return completed.stdout.strip()


class LibvirtLabProvider:
    def __init__(
        self,
        *,
        runner: CommandRunner,
        storage_root: str = "/var/lib/jason-lab/vms",
        isolated_network: str = "jason-lab-isolated",
    ) -> None:
        self._runner = runner
        self._storage_root = Path(storage_root)
        self._isolated_network = isolated_network

    def create(self, spec: LabVmSpec) -> str:
        if "/" in spec.vm_id or ".." in spec.vm_id:
            raise LabInfrastructureError("Unsafe lab VM identity.")
        disk_path = self._storage_root / f"{spec.vm_id}.qcow2"
        self._runner.run(
            [
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                str(disk_path),
                f"{spec.disk_gib}G",
            ]
        )
        self._runner.run(
            [
                "virt-install",
                "--name",
                spec.vm_id,
                "--memory",
                str(spec.memory_mib),
                "--vcpus",
                str(spec.vcpus),
                "--disk",
                f"path={disk_path},format=qcow2,bus=virtio",
                "--cdrom",
                spec.image_path,
                "--network",
                f"network={self._isolated_network},model=virtio",
                "--boot",
                "uefi",
                "--tpm",
                "backend.type=emulator,backend.version=2.0,model=tpm-crb",
                "--os-variant",
                "win11",
                "--graphics",
                "spice",
                "--noautoconsole",
                "--noreboot",
            ]
        )
        return spec.vm_id

    def start(self, provider_id: str) -> None:
        self._runner.run(["virsh", "start", provider_id])

    def stop(self, provider_id: str) -> None:
        self._runner.run(["virsh", "shutdown", provider_id])

    def delete(self, provider_id: str) -> None:
        self._runner.run(
            [
                "virsh",
                "undefine",
                provider_id,
                "--nvram",
                "--tpm",
                "--remove-all-storage",
            ]
        )

    def snapshot_create(self, provider_id: str, name: str) -> None:
        self._runner.run(
            [
                "virsh",
                "snapshot-create-as",
                provider_id,
                name,
                "--description",
                "Jason governed lab baseline",
                "--atomic",
            ]
        )

    def snapshot_revert(self, provider_id: str, name: str) -> None:
        self._runner.run(["virsh", "snapshot-revert", provider_id, name])

    def snapshot_delete(self, provider_id: str, name: str) -> None:
        self._runner.run(["virsh", "snapshot-delete", provider_id, name])

    def state(self, provider_id: str) -> LabAssetState:
        raw = self._runner.run(["virsh", "domstate", provider_id]).strip().lower()
        if raw in {"running", "idle", "paused", "pmsuspended"}:
            return LabAssetState.RUNNING
        if raw in {"shut off", "shutdown", "crashed"}:
            return LabAssetState.STOPPED if raw != "crashed" else LabAssetState.ERROR
        return LabAssetState.ERROR
