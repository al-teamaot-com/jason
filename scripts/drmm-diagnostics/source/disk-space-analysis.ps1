# AOT Disk Space Analysis - read-only, bounded filesystem and storage diagnostics.
$report = New-AotReport 'disk-space-analysis'
$maxFiles = 40000
$maxSecondsPerVolume = 25
$maxTotalScanSeconds = 75
$maxFoldersPerVolume = 32
Invoke-AotSection $report 'volumes_and_health' {
    $items = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' -ErrorAction Stop | ForEach-Object {
        $pct = if ($_.Size -gt 0) { [Math]::Round(100.0 * $_.FreeSpace / $_.Size, 1) } else { $null }
        if ($null -ne $pct -and $pct -le 15) {
            Add-AotFinding $report 'warning' 'LOW_DISK_SPACE' ($_.DeviceID + ' has ' + $pct + '% free')
        }
        [ordered]@{ drive = $_.DeviceID; label = Limit-AotText $_.VolumeName 80; filesystem = $_.FileSystem
            total_gb = [Math]::Round([double]$_.Size / 1GB, 2)
            free_gb = [Math]::Round([double]$_.FreeSpace / 1GB, 2); free_percent = $pct }
    })
    return @{ data = $items }
}
Invoke-AotSection $report 'physical_disks' {
    $warnings = @(); $data = @()
    try {
        if (Get-Command Get-PhysicalDisk -ErrorAction SilentlyContinue) {
            $data = @(Get-PhysicalDisk -ErrorAction Stop | Select-Object -First 20 | ForEach-Object {
                [ordered]@{ friendly_name = Limit-AotText $_.FriendlyName 90
                    media_type = [string]$_.MediaType; health = [string]$_.HealthStatus
                    operational_status = [string]($_.OperationalStatus -join ',')
                    size_gb = [Math]::Round([double]$_.Size / 1GB, 2) }
            })
        } else { $warnings += 'Storage cmdlets not available on this OS' }
    } catch { $warnings += 'Physical disk health unavailable: ' + (Limit-AotText $_.Exception.Message 130) }
    return @{ data = $data; warnings = $warnings }
}
function Measure-AotFolderTree {
    param([string]$Root, [int]$FileBudget, [int]$SecondsBudget)
    $stack = New-Object System.Collections.Stack
    $stack.Push($Root)
    $bytes = [double]0
    $files = 0
    $directories = 0
    $denied = 0
    $skippedLinks = 0
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $stoppedFor = ''
    while ($stack.Count -gt 0) {
        if ($files -ge $FileBudget) { $stoppedFor = 'file_budget'; break }
        if ($stopwatch.Elapsed.TotalSeconds -gt $SecondsBudget) { $stoppedFor = 'time_budget'; break }
        $folder = [string]$stack.Pop()
        try {
            $it = [IO.Directory]::EnumerateFileSystemEntries($folder).GetEnumerator()
            try {
                while ($it.MoveNext()) {
                    if ($files -ge $FileBudget) { $stoppedFor = 'file_budget'; break }
                    if ($stopwatch.Elapsed.TotalSeconds -gt $SecondsBudget) { $stoppedFor = 'time_budget'; break }
                    $entry = [string]$it.Current
                    try {
                        $attr = [IO.File]::GetAttributes($entry)
                        if (($attr -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                            $skippedLinks++; continue
                        }
                        if (($attr -band [IO.FileAttributes]::Directory) -ne 0) {
                            $directories++; $stack.Push($entry)
                        } else {
                            $files++
                            try { $bytes += [double]([IO.FileInfo]$entry).Length }
                            catch { $denied++ }
                        }
                    } catch { $denied++ }
                }
            } finally { if ($it -is [IDisposable]) { $it.Dispose() } }
        } catch { $denied++ }
        if ($stoppedFor) { break }
    }
    $stopwatch.Stop()
    return [ordered]@{
        size_gb = [Math]::Round($bytes / 1GB, 3)
        counted_files = $files; counted_directories = $directories
        inaccessible_entries = $denied; skipped_links = $skippedLinks
        complete = ($stack.Count -eq 0 -and !$stoppedFor -and $denied -eq 0)
        bounded_reason = $stoppedFor
        elapsed_seconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
        note = 'Measured bytes are a lower bound if enumeration is partial, inaccessible or capped.'
    }
}
Invoke-AotSection $report 'top_level_folder_usage' {
    $volumes = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' -ErrorAction Stop | Select-Object -First 6)
    $out = @()
    $warnings = @()
    $globalScan = [Diagnostics.Stopwatch]::StartNew()
    foreach ($vol in $volumes) {
        $drive = $vol.DeviceID + '\'
        $rootDirectories = @()
        try {
            $rootDirectories = @([IO.Directory]::EnumerateDirectories($drive) | Select-Object -First $maxFoldersPerVolume)
        } catch {
            $warnings += ('Cannot enumerate ' + $drive + ': ' + (Limit-AotText $_.Exception.Message 130))
            continue
        }
        if ($rootDirectories.Count -ge $maxFoldersPerVolume) {
            $warnings += ($drive + ' directory count capped at ' + $maxFoldersPerVolume)
        }
        $time = [Diagnostics.Stopwatch]::StartNew()
        $inspected = @()
        $usedFiles = 0
        foreach ($directory in $rootDirectories) {
            $remainingSeconds = [Math]::Min(($maxSecondsPerVolume - [int]$time.Elapsed.TotalSeconds), ($maxTotalScanSeconds - [int]$globalScan.Elapsed.TotalSeconds))
            $remainingFiles = $maxFiles - $usedFiles
            if ($remainingSeconds -le 0 -or $remainingFiles -le 0) {
                $warnings += ($drive + ' traversal reached budget; remaining folders unmeasured')
                break
            }
            $a = Get-Item -LiteralPath $directory -Force -ErrorAction SilentlyContinue
            if ($null -eq $a) { continue }
            if (($a.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
            $usage = Measure-AotFolderTree -Root $directory -FileBudget $remainingFiles -SecondsBudget $remainingSeconds
            $usedFiles += $usage.counted_files
            if (!$usage.complete) { $warnings += ('Partial measurement: ' + (Limit-AotText $directory 90)) }
            $inspected += [ordered]@{ folder = (Limit-AotText $directory 180); usage = $usage }
        }
        $time.Stop()
        $out += [ordered]@{ volume = $vol.DeviceID
            top_folders_by_measured_bytes = @($inspected | Sort-Object { $_.usage.size_gb } -Descending | Select-Object -First 15)
            inspected_folders = $inspected.Count
            measured_files = $usedFiles; elapsed_seconds = [Math]::Round($time.Elapsed.TotalSeconds,1)
            complete_scan = ($warnings.Count -eq 0 -and $inspected.Count -eq $rootDirectories.Count) }
    }
    $globalScan.Stop()
    if ($volumes.Count -ge 6) { $warnings += 'Volume inventory capped at six fixed volumes' }
    return @{ data = $out; warnings = $warnings }
}
Invoke-AotSection $report 'known_consumers' {
    $paths = @(
        @{ key = 'windows_temp'; value = (Join-Path $env:SystemRoot 'Temp') }
        @{ key = 'update_download'; value = (Join-Path $env:SystemRoot 'SoftwareDistribution\Download') }
        @{ key = 'sysmon'; value = (Join-Path $env:SystemDrive 'Sysmon') }
        @{ key = 'crash_dumps'; value = (Join-Path $env:SystemRoot 'Minidump') }
        @{ key = 'windows_error_reporting'; value = (Join-Path $env:ProgramData 'Microsoft\Windows\WER') }
        @{ key = 'programdata_temp'; value = (Join-Path $env:ProgramData 'Temp') }
    )
    $items = @()
    $warnings = @()
    foreach ($item in $paths) {
        if (!(Test-Path -LiteralPath $item.value -PathType Container)) {
            $items += @{ category = $item.key; present = $false }; continue
        }
        $result = Measure-AotFolderTree -Root $item.value -FileBudget 6000 -SecondsBudget 8
        $items += @{ category = $item.key; present = $true; path = $item.value; usage = $result }
        if (!$result.complete) { $warnings += $item.key + ' is a partial lower-bound size measurement' }
        if ($item.key -eq 'sysmon' -and $result.size_gb -ge 5) {
            Add-AotFinding $report 'warning' 'SYSMON_USAGE' ('C:\Sysmon approximately ' + $result.size_gb + ' GB counted')
        }
    }
    return @{ data = $items; warnings = $warnings }
}
Invoke-AotSection $report 'pagefile_shadow_and_vss' {
    $warnings = @(); $data = [ordered]@{}
    try {
        $data.pagefiles = @(Get-CimInstance Win32_PageFileUsage -ErrorAction Stop | ForEach-Object {
            @{ drive_path = Limit-AotText $_.Name 120; allocated_mb = $_.AllocatedBaseSize; used_mb = $_.CurrentUsage }
        })
    } catch { $warnings += 'Pagefile read unavailable' }
    try {
        $data.shadowstorage = @(Get-CimInstance Win32_ShadowStorage -ErrorAction Stop | Select-Object Volume,AllocatedSpace,UsedSpace,MaxSpace)
    } catch { $warnings += 'Shadow storage unavailable: ' + (Limit-AotText $_.Exception.Message 110) }
    try {
        $data.vss_writers_excerpt = Limit-AotText ((& "$env:SystemRoot\System32\vssadmin.exe" 'list' 'writers' 2>&1) -join ' ') 1000
    } catch { $warnings += 'VSS writers unavailable' }
    return @{ data = $data; warnings = $warnings }
}
Invoke-AotSection $report 'storage_events' {
    $events = Get-AotEvents -LogName 'System' -EventIds @(7,11,15,51,55,57,129,153,157) -Days 7 -Limit 40
    if (@($events.data).Count -gt 0) {
        Add-AotFinding $report 'warning' 'STORAGE_EVENTS' ([string]@($events.data).Count + ' relevant storage events in sampled window')
    }
    return @{ data = $events.data; warnings = $events.warnings }
}
Write-AotReport $report
