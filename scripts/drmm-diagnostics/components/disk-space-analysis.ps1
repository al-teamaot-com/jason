# AOT - Disk Space Analysis [WIN]
# Standalone DRMM script; generated - do not edit manually.
# AOT DRMM diagnostic shared source. Build embeds this verbatim into each standalone component.
# PowerShell 5.1 / SYSTEM compatible. No remediation, state writes, module installation or prompts.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$AotDiagnosticStartedUtc = [DateTime]::UtcNow

function New-AotReport {
    param([string]$Component)
    return [ordered]@{
        schema_version = '1.0'
        component = $Component
        read_only = $true
        collection_utc = [DateTime]::UtcNow.ToString('o')
        computer = $env:COMPUTERNAME
        runtime = [ordered]@{
            powershell = $PSVersionTable.PSVersion.ToString()
            identity_is_system = ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -eq 'S-1-5-18')
        }
        sections = (New-Object System.Collections.ArrayList)
        findings = (New-Object System.Collections.ArrayList)
        limitations = (New-Object System.Collections.ArrayList)
        overall_status = 'unknown'
        duration_ms = 0
    }
}

function Add-AotFinding {
    param($Report, [string]$Severity, [string]$Code, [string]$Message)
    [void]$Report.findings.Add([ordered]@{
        severity = $Severity; code = $Code; message = $Message
    })
}

function Invoke-AotSection {
    param($Report, [string]$Name, [scriptblock]$Collect)
    $t = [Diagnostics.Stopwatch]::StartNew()
    $status = 'complete'
    $data = $null
    $warnings = @()
    try {
        $result = & $Collect
        if ($null -ne $result) {
            $data = $result.data
            if ($null -ne $result.warnings) {
                $warnings = @($result.warnings | Where-Object { $null -ne $_ -and [string]$_ -ne '' })
            }
            if ($result.incomplete -eq $true -or $warnings.Count -gt 0) { $status = 'partial' }
            if ($result.not_applicable -eq $true) { $status = 'not_applicable' }
        } else {
            $status = 'unavailable'
            $warnings = @('Collector returned no data')
        }
    } catch {
        $status = 'unavailable'
        $warnings = @('Collector error: ' + $_.Exception.GetType().Name + ': ' + (Limit-AotText $_.Exception.Message 180))
    }
    $t.Stop()
    [void]$Report.sections.Add([ordered]@{
        name = $Name; status = $status; duration_ms = $t.ElapsedMilliseconds
        data = $data; warnings = $warnings
    })
}

function Limit-AotText {
    param($Value, [int]$Length = 220)
    if ($null -eq $Value) { return '' }
    $s = [string]$Value
    $s = $s -replace '[\r\n\t]+', ' '
    if ($s.Length -gt $Length) { return $s.Substring(0, $Length) + '...' }
    return $s
}

function Get-AotEvents {
    param([string]$LogName, [int[]]$EventIds, [int]$Days = 3, [int]$Limit = 20)
    $from = (Get-Date).AddDays(-[Math]::Min([Math]::Max($Days, 1), 14))
    $limitSafe = [Math]::Min([Math]::Max($Limit, 1), 40)
    $warnings = @()
    $items = @()
    try {
        $events = @(Get-WinEvent -FilterHashtable @{
            LogName = $LogName; ID = $EventIds; StartTime = $from
        } -MaxEvents $limitSafe -ErrorAction Stop)
        $items = @($events | ForEach-Object {
            [ordered]@{
                when = $_.TimeCreated.ToUniversalTime().ToString('o')
                id = $_.Id
                provider = Limit-AotText $_.ProviderName 90
                level = $_.LevelDisplayName
                message = Limit-AotText $_.Message 280
            }
        })
    } catch {
        $m = [string]$_.Exception.Message
        if ($_.FullyQualifiedErrorId -notmatch 'NoMatchingEventsFound' -and $m -notmatch 'No events were found') {
            $warnings += ('Event read incomplete: ' + (Limit-AotText $m 150))
        }
    }
    return @{ data = $items; warnings = $warnings }
}

function Get-AotPendingReboot {
    $checks = [ordered]@{
        windows_update = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
        component_servicing = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'
        pending_file_renames = $false
    }
    try {
        $p = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name 'PendingFileRenameOperations' -ErrorAction Stop
        $checks.pending_file_renames = (@($p.PendingFileRenameOperations).Count -gt 0)
    } catch {}
    return $checks
}

function Get-AotTimeStatus {
    $source = ''
    $status = ''
    try { $source = Limit-AotText ((& "$env:SystemRoot\System32\w32tm.exe" '/query' '/source' 2>&1) -join ' ') 180 } catch {}
    try { $status = Limit-AotText ((& "$env:SystemRoot\System32\w32tm.exe" '/query' '/status' 2>&1) -join ' ') 500 } catch {}
    return [ordered]@{ source = $source; status_excerpt = $status }
}

function Write-AotReport {
    param($Report)
    $incomplete = @($Report.sections | Where-Object { $_.status -eq 'partial' -or $_.status -eq 'unavailable' })
    if ($Report.sections.Count -eq 0 -or @($Report.sections | Where-Object {$_.status -eq 'complete' -or $_.status -eq 'partial'}).Count -eq 0) {
        $Report.overall_status = 'unavailable'
    } elseif ($incomplete.Count -gt 0) {
        $Report.overall_status = 'partial'
    } else {
        $Report.overall_status = 'complete'
    }
    $Report.duration_ms = [int]([DateTime]::UtcNow - $AotDiagnosticStartedUtc).TotalMilliseconds
    Write-Output ('AOT DIAGNOSTIC | ' + $Report.component + ' | ' + $env:COMPUTERNAME)
    Write-Output ('Collection=' + $Report.overall_status + ' | Sections=' + $Report.sections.Count + ' | Findings=' + $Report.findings.Count + ' | DurationMs=' + $Report.duration_ms)
    foreach ($f in @($Report.findings | Select-Object -First 20)) {
        Write-Output ('[' + $f.severity + '] ' + $f.code + ': ' + $f.message)
    }
    foreach ($s in @($incomplete | Select-Object -First 15)) {
        Write-Output ('[COLLECTION ' + $s.status + '] ' + $s.name + ': ' + ((@($s.warnings) | Select-Object -First 2) -join ' | '))
    }
    Write-Output 'AOT_DIAGNOSTIC_JSON_BEGIN'
    Write-Output (ConvertTo-Json -InputObject $Report -Depth 15 -Compress)
    Write-Output 'AOT_DIAGNOSTIC_JSON_END'
    if ($Report.overall_status -eq 'unavailable') { exit 1 }
    exit 0
}

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
