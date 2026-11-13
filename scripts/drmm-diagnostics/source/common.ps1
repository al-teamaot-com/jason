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
