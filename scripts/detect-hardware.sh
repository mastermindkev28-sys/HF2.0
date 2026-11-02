#!/usr/bin/env bash
# Higgsfield Studio hardware check (macOS / Linux). Read-only: prints info, changes nothing.
# Run:  bash detect-hardware.sh
echo "=== OS ==="; uname -a
if [ "$(uname)" = "Darwin" ]; then
  sw_vers
  echo "=== CPU / Chip ==="; sysctl -n machdep.cpu.brand_string
  echo "=== RAM (GB) ==="; echo $(( $(sysctl -n hw.memsize) / 1073741824 ))
  echo "=== GPU ==="; system_profiler SPDisplaysDataType | grep -E "Chipset|Cores|Metal|VRAM"
else
  [ -f /etc/os-release ] && grep PRETTY_NAME /etc/os-release
  echo "=== CPU ==="; lscpu | grep -E "Model name|^CPU\(s\)"
  echo "=== RAM ==="; free -g | head -2
  echo "=== GPU ==="; lspci 2>/dev/null | grep -Ei "vga|3d|display"
  command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv
  command -v rocm-smi >/dev/null && rocm-smi --showproductname --showmeminfo vram
fi
echo "=== Disk ==="; df -h "$HOME"
echo "=== Tools ==="
for t in python3 git node ffmpeg; do if command -v $t >/dev/null; then echo "$t: $($t --version 2>&1 | head -1)"; else echo "$t: not installed"; fi; done
