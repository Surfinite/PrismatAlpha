# Get local PrismataAI process stats + system health
# Output: JSON for dashboard consumption
# IMPORTANT: NO Get-Counter calls — they block ~1s each and cause UI stutter

$result = @{
    selfplay = @{ processes = 0; threads = 0; pids = @() }
    training = @{ processes = 0; workers = 0; pids = @(); device = 'cpu'; model_label = '' }
    claude = @{ processes = 0; ram_mb = 0; cpu_sec = 0 }
    cpu_percent = 0
    gpu_percent = 0
    gpu_mem_mb = 0
    system = @{
        ram_used_gb = 0; ram_total_gb = 0; ram_percent = 0
        committed_gb = 0; page_faults_sec = 0
        disk_read_mbsec = 0; disk_write_mbsec = 0; disk_queue = 0
    }
}

# --- Selfplay processes ---
$selfplayProcs = @(Get-Process -Name 'Prismata_Testing*','Prismata_Standalone*' -ErrorAction SilentlyContinue)
$result.selfplay.processes = $selfplayProcs.Count
$result.selfplay.pids = @($selfplayProcs | ForEach-Object { $_.Id })
foreach ($p in $selfplayProcs) {
    $result.selfplay.threads += $p.Threads.Count
}

# --- Training processes ---
$allPython = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' })
$trainProcs = @()
$workerPids = @()
foreach ($p in $allPython) {
    if ($p.CommandLine -match 'train\.py' -and $p.CommandLine -notmatch 'spawn_main' -and $p.CommandLine -notmatch '\s+-c\s') {
        $trainProcs += $p
        if ($p.CommandLine -match '--device\s+xpu') { $result.training.device = 'xpu' }
        if ($p.CommandLine -match 'training[/\\]models[/\\](\S+)') { $result.training.model_label = $Matches[1] }
        if ($p.CommandLine -match '--num-workers\s+(\d+)') { $result.training.workers = [int]$Matches[1] }
    }
    elseif ($p.CommandLine -match 'spawn_main.*parent_pid=(\d+)') {
        $parentPid = [int]$Matches[1]
        if ($allPython | Where-Object { $_.ProcessId -eq $parentPid -and $_.CommandLine -match 'train\.py' }) {
            $workerPids += $p.ProcessId
        }
    }
}
$result.training.processes = @($trainProcs).Count
# Workers: prefer --num-workers from cmdline (set above), fallback to spawn_main count
if ($result.training.workers -eq 0) { $result.training.workers = @($workerPids).Count }
$result.training.pids = @($trainProcs | ForEach-Object { $_.ProcessId })

# --- Claude Code processes (node.exe running claude-code) ---
try {
    $allNode = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'node' })
    $claudePids = @()
    foreach ($n in $allNode) {
        if ($n.CommandLine -match 'claude|anthropic') {
            $claudePids += $n.ProcessId
        }
    }
    $result.claude.processes = $claudePids.Count
    if ($claudePids.Count -gt 0) {
        $claudeRam = 0
        $claudeCpu = 0
        foreach ($cpid in $claudePids) {
            $cproc = Get-Process -Id $cpid -ErrorAction SilentlyContinue
            if ($cproc) {
                $claudeRam += $cproc.WorkingSet64
                $claudeCpu += $cproc.TotalProcessorTime.TotalSeconds
            }
        }
        $result.claude.ram_mb = [math]::Round($claudeRam / 1MB, 0)
        $result.claude.cpu_sec = [math]::Round($claudeCpu, 0)
    }
} catch {}

# --- CPU utilization (from cumulative process CPU time) ---
$ourPids = @($result.selfplay.pids) + @($result.training.pids) + @($workerPids)
if ($ourPids.Count -gt 0) {
    try {
        $totalCpuSec = 0
        $avgWallSec = 0
        $count = 0
        foreach ($procId in $ourPids) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc -and $proc.StartTime) {
                $totalCpuSec += $proc.TotalProcessorTime.TotalSeconds
                $avgWallSec += (Get-Date).Subtract($proc.StartTime).TotalSeconds
                $count++
            }
        }
        $cpuCount = [Environment]::ProcessorCount
        if ($count -gt 0 -and $avgWallSec -gt 0) {
            $wallPerProc = $avgWallSec / $count
            $result.cpu_percent = [math]::Round(($totalCpuSec / ($wallPerProc * $cpuCount)) * 100, 1)
        }
    } catch {}
}

# --- GPU utilization (via WMI — instant, no Get-Counter) ---
try {
    # Query GPU engine utilization from CIM (Win10+ / Win11)
    $gpuEngines = Get-CimInstance -Namespace 'root/cimv2' -ClassName 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'engtype_3D' }
    if ($gpuEngines) {
        $gpuTotal = ($gpuEngines | Measure-Object -Property UtilizationPercentage -Sum).Sum
        $result.gpu_percent = [math]::Round($gpuTotal, 1)
    }
} catch {}

# --- GPU memory (via WMI — instant) ---
try {
    $gpuMem = Get-CimInstance -Namespace 'root/cimv2' -ClassName 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory' -ErrorAction SilentlyContinue
    if ($gpuMem) {
        $ourGpuMem = 0
        foreach ($item in $gpuMem) {
            if ($item.Name -match 'pid_(\d+)' -and [int]$Matches[1] -in $ourPids) {
                $ourGpuMem += $item.DedicatedUsage
            }
        }
        $result.gpu_mem_mb = [math]::Round($ourGpuMem / 1MB, 0)
    }
} catch {}

# --- System health ---
# RAM
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    $freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    $usedGB = [math]::Round($totalGB - $freeGB, 1)
    $result.system.ram_total_gb = $totalGB
    $result.system.ram_used_gb = $usedGB
    $result.system.ram_percent = [math]::Round(($usedGB / $totalGB) * 100, 0)
} catch {}

# Memory counters (page faults, committed bytes — instant via CIM)
try {
    $perf = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction SilentlyContinue
    if ($perf) {
        $result.system.page_faults_sec = [int]$perf.PageFaultsPersec
        $result.system.committed_gb = [math]::Round($perf.CommittedBytes / 1GB, 1)
    }
} catch {}

# Disk I/O (instant via CIM)
try {
    $disk = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter 'Name="_Total"' -ErrorAction SilentlyContinue
    if ($disk) {
        $result.system.disk_queue = [math]::Round($disk.CurrentDiskQueueLength, 0)
        $result.system.disk_read_mbsec = [math]::Round($disk.DiskReadBytesPersec / 1MB, 1)
        $result.system.disk_write_mbsec = [math]::Round($disk.DiskWriteBytesPersec / 1MB, 1)
    }
} catch {}

$result | ConvertTo-Json -Compress
