# Governed Lab Infrastructure

## Purpose
Jason uses disposable lab virtual machines to test components, PowerShell, playbooks, disruption classification, and regression behavior without using client or production endpoints.

## Constitutional boundary
Lab assets are not production/client assets. Successful lab execution never expands authority for production execution.

## Required host state
A lab hypervisor must be explicitly approved and registered as lab-only. It must expose hardware virtualization/KVM, QEMU/libvirt, UEFI Secure Boot firmware, software TPM support, sufficient capacity, and isolated networking.

The host-readiness tool reports LAB_HOST_READY=false whenever a required prerequisite is absent.

## VM guardrails
All VMs must use an approved image, fixed CPU/RAM/disk limits, isolated networking, Secure Boot, TPM, no client data, no production-domain join, and a baseline snapshot before reusable acceptance/regression testing.

## Lifecycle
1. Discover and verify an approved lab host.
2. Validate the VM spec against host limits and approved images.
3. Create the disposable VM through the governed provider.
4. Provision Windows unattended when an approved image and answer file exist.
5. Verify boot/readiness.
6. Stop the VM and create a known-good baseline snapshot.
7. Run bounded tests.
8. Revert to baseline before subsequent independent tests.
9. Delete disposable assets when no longer required.

## Acceptance evidence
Acceptance requires a real Windows 11 Pro VM on an approved hypervisor, Secure Boot and TPM verification, boot/readiness verification, baseline snapshot creation, a synthetic state change, verified baseline revert, and final deletion or return to baseline.

## Current Jason-host result - 2026-09-27
The physical Jason host has enough RAM and disk for a small lab VM, but firmware is not exposing Intel VT-x/AMD-V and /dev/kvm is absent. QEMU/libvirt/OVMF/swtpm are also not installed. No privilege bypass is permitted.

Repository implementation can therefore be validated now, but physical Windows 11 acceptance remains blocked until virtualization is enabled in firmware/BIOS or another approved hypervisor is registered, and the hypervisor prerequisites are installed.
