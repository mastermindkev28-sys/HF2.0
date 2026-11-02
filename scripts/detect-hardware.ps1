# Higgsfield Studio hardware check (Windows). Read-only: prints info, changes nothing.
# Run in PowerShell:  powershell -ExecutionPolicy Bypass -File detect-hardware.ps1
"=== OS ==="
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture | Format-List
"=== CPU ==="
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors | Format-List
"=== RAM (GB) ==="
[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
"=== GPU(s) ==="
Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, AdapterRAM | Format-List
"=== NVIDIA details (if present) ==="
try { nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv } catch { "nvidia-smi not found" }
"=== Disks (GB free / total) ==="
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object { "{0}  {1} free / {2} total" -f $_.DeviceID, [math]::Round($_.FreeSpace/1GB), [math]::Round($_.Size/1GB) }
"=== Tools ==="
foreach ($t in "python","git","node","ffmpeg") { $c = Get-Command $t -ErrorAction SilentlyContinue; if ($c) { "$t : " + (& $t --version 2>&1 | Select-Object -First 1) } else { "$t : not installed" } }
