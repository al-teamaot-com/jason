from __future__ import annotations

from kernel.lab_infrastructure import LabAssetState, LabVmSpec, LibvirtLabProvider


class RecordingRunner:
    def __init__(self) -> None:
        self.calls = []
        self.domstate = "shut off"

    def run(self, argv):
        self.calls.append(list(argv))
        if list(argv)[:2] == ["virsh", "domstate"]:
            return self.domstate
        return ""


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


def test_create_uses_isolated_network_tpm_uefi_and_fixed_resources() -> None:
    runner = RecordingRunner()
    provider = LibvirtLabProvider(runner=runner)

    provider_id = provider.create(spec())

    assert provider_id == "win11-regression-01"
    assert runner.calls[0] == [
        "qemu-img",
        "create",
        "-f",
        "qcow2",
        "/var/lib/jason-lab/vms/win11-regression-01.qcow2",
        "64G",
    ]
    create = runner.calls[1]
    assert create[0] == "virt-install"
    assert "network=jason-lab-isolated,model=virtio" in create
    assert "backend.type=emulator,backend.version=2.0,model=tpm-crb" in create
    assert "uefi" in create
    assert "4096" in create
    assert "2" in create


def test_provider_lifecycle_commands_are_bounded() -> None:
    runner = RecordingRunner()
    provider = LibvirtLabProvider(runner=runner)

    provider.start("lab1")
    provider.stop("lab1")
    provider.snapshot_create("lab1", "baseline")
    provider.snapshot_revert("lab1", "baseline")
    provider.snapshot_delete("lab1", "baseline")
    provider.delete("lab1")

    assert ["virsh", "start", "lab1"] in runner.calls
    assert ["virsh", "shutdown", "lab1"] in runner.calls
    assert ["virsh", "snapshot-revert", "lab1", "baseline"] in runner.calls
    assert ["virsh", "snapshot-delete", "lab1", "baseline"] in runner.calls
    assert [
        "virsh",
        "undefine",
        "lab1",
        "--nvram",
        "--tpm",
        "--remove-all-storage",
    ] in runner.calls


def test_provider_maps_hypervisor_state() -> None:
    runner = RecordingRunner()
    provider = LibvirtLabProvider(runner=runner)

    runner.domstate = "running"
    assert provider.state("lab1") is LabAssetState.RUNNING

    runner.domstate = "shut off"
    assert provider.state("lab1") is LabAssetState.STOPPED

    runner.domstate = "crashed"
    assert provider.state("lab1") is LabAssetState.ERROR
