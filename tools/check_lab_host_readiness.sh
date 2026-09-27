#!/usr/bin/env bash
set -eu

reason_count=0
emit_reason() {
  printf "REASON=%s\n" "$1"
  reason_count=$((reason_count + 1))
}

printf "HOSTNAME=%s\n" "$(hostname)"
virt="$(systemd-detect-virt 2>/dev/null || true)"
if [ "$virt" = "none" ]; then
  printf "BARE_METAL=true\n"
else
  printf "BARE_METAL=false\n"
  emit_reason "host is virtualized: $virt"
fi

if grep -Eq "(vmx|svm)" /proc/cpuinfo; then
  printf "HARDWARE_VIRTUALIZATION=true\n"
else
  printf "HARDWARE_VIRTUALIZATION=false\n"
  emit_reason "CPU virtualization is not exposed"
fi

if [ -e /dev/kvm ]; then
  printf "KVM_DEVICE=true\n"
else
  printf "KVM_DEVICE=false\n"
  emit_reason "/dev/kvm is absent"
fi

for command_name in virsh qemu-system-x86_64 swtpm; do
  if command -v "$command_name" >/dev/null 2>&1; then
    printf "%s_AVAILABLE=true\n" "$(printf "%s" "$command_name" | tr "a-z-" "A-Z_")"
  else
    printf "%s_AVAILABLE=false\n" "$(printf "%s" "$command_name" | tr "a-z-" "A-Z_")"
    emit_reason "$command_name is not installed"
  fi
done

if find /usr/share/OVMF /usr/share/edk2 -type f -iname "*code*.fd" 2>/dev/null | grep -q .; then
  printf "OVMF_AVAILABLE=true\n"
else
  printf "OVMF_AVAILABLE=false\n"
  emit_reason "UEFI/OVMF firmware is not installed"
fi

printf "FREE_MEMORY_MIB=%s\n" "$(awk "/MemAvailable:/ {print int(\$2/1024)}" /proc/meminfo)"
printf "FREE_DISK_GIB=%s\n" "$(df -Pk / | awk "NR==2 {print int(\$4/1024/1024)}")"
if [ "$reason_count" -eq 0 ]; then
  printf "LAB_HOST_READY=true\n"
else
  printf "LAB_HOST_READY=false\n"
fi
