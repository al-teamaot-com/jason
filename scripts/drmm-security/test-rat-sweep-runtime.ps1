#requires -Version 5.1
# Execute only against an isolated ephemeral Windows CI runner.
# This test does not print process paths, remote IPs or the raw JSON.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SourcePath)
$ErrorActionPreference='Stop'
$raw=@(& powershell.exe -NoProfile -NonInteractive -File $SourcePath 2>&1)
$exitCode=$LASTEXITCODE
if($exitCode -ne 0){throw ('Report-only script returned '+$exitCode)}
$lines=@($raw | ForEach-Object { [string]$_ })
if($lines.Count -lt 5 -or $lines[0] -ne '<-Start Result->'){throw 'Missing Datto result header'}
$begin=[array]::IndexOf($lines,'AOT_SECURITY_JSON_BEGIN')
$end=[array]::IndexOf($lines,'AOT_SECURITY_JSON_END')
if($begin -lt 0 -or $end -lt 0 -or $end -le $begin){throw 'Missing JSON report boundary markers'}
$json=($lines[($begin+1)..($end-1)] -join '')
if($json.Length -gt 59000){throw 'Report JSON exceeds bounded output'}
$report=$json | ConvertFrom-Json -ErrorAction Stop
if($report.schema_version -ne '1.0'){throw 'Schema incompatible'}
if($report.read_only -ne $true){throw 'Read-only marker missing'}
if([int]$report.scanned.processes -lt 10){throw 'Unreasonable process inventory on Windows CI runner'}
if($null -eq $report.defender_coverage -or $null -eq $report.optional_sections){
    throw 'Required Defender coverage metadata missing'
}
if($report.defender_coverage.preferences_status -eq 'skipped_inactive'){
    if(-not @($report.optional_sections | Where-Object {$_.section -eq 'DefenderPreference'}).Count){
        throw 'Inactive Defender preference skipped without coverage evidence'
    }
}
$summary=(($lines | Where-Object {$_ -match '^Coverage \| DefenderAV='}) -join ';')
if(-not $summary){throw 'Early bounded coverage summary missing'}
Write-Output ('AOT_RAT_SWEEP_RUNTIME=PASS Collection='+$report.collection_status+
    ' Processes='+$report.scanned.processes+
    ' High='+$report.summary.high+
    ' DefenderAV='+$report.defender_coverage.antivirus_status+
    ' Pref='+$report.defender_coverage.preferences_status)
