# Datto AV Force Update [WIN] AOT Ver 09172026-1
#
# Purpose:
#   Run exactly one Datto AV refresh through the active HUNTAgent binary.
#
# Safety contract:
#   - Windows PowerShell 5.1 compatible.
#   - No input variables and no arbitrary command execution.
#   - The active HUNTAgent service determines the executable path.
#   - Only the two known Datto EDR installation paths are accepted.
#   - The executable must have a valid Authenticode signature.
#   - An already-running `datto-av --force-update` is never duplicated.
#   - The command is bounded to five minutes of observation. If it is still
#     active, the component returns PendingReboot and leaves the process alone.
#   - Component completion is never proof that Datto AV is healthy; Jason must
#     rerun the dedicated EDR/AV health component afterward.

$ErrorActionPreference = 'Stop'

$ComponentName = 'Datto AV Force Update [WIN] AOT Ver 09172026-1'
$MaxWaitSeconds = 300
$PollSeconds = 5
$AllowedAgentPaths = @(
    'C:\ProgramData\CentraStage\AEMAgent\RMM.AdvancedThreatDetection\agent.exe',
    'C:\Program Files\Infocyte\agent\agent.exe'
)

function Write-ResultBlock {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Summary
    )

    Write-Output '<-Start Result->'
    Write-Output ("Status={0} Summary={1}" -f $Status, $Summary)
    Write-Output '<-End Result->'
}

function Write-DiagnosticBlock {
    param([string[]]$Lines)

    Write-Output '<-Start Diagnostic->'
    foreach ($Line in $Lines) {
        Write-Output $Line
    }
    Write-Output '<-End Diagnostic->'
}

function Stop-WithResult {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Summary,
        [int]$ExitCode = 1,
        [string[]]$Diagnostic = @()
    )

    Write-ResultBlock -Status $Status -Summary $Summary
    Write-DiagnosticBlock -Lines $Diagnostic
    exit $ExitCode
}

function Get-AgentExecutablePath {
    param([Parameter(Mandatory = $true)][string]$ServicePath)

    $Text = $ServicePath.Trim()

    if ($Text -match '^\s*"([^"]+\.exe)"') {
        return $Matches[1]
    }

    if ($Text -match '^\s*(.+?\.exe)(?:\s|$)') {
        return $Matches[1].Trim()
    }

    return $null
}

function Test-AllowedAgentPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    foreach ($Allowed in $AllowedAgentPaths) {
        if ([string]::Equals($Path, $Allowed, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Get-ForceUpdateProcesses {
    $Processes = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='agent.exe'" -ErrorAction SilentlyContinue)

    return @(
        $Processes | Where-Object {
            $_.CommandLine -and $_.CommandLine -match '(?i)(?:^|\s)datto-av\s+--force-update(?:\s|$)'
        }
    )
}

try {
    $Service = Get-CimInstance -ClassName Win32_Service -Filter "Name='HUNTAgent'" -ErrorAction SilentlyContinue

    if ($null -eq $Service) {
        Stop-WithResult \
            -Status 'AgentNotReady' \
            -Summary 'HUNTAgent service is not installed. Repair EDR before attempting Datto AV refresh.' \
            -Diagnostic @('HUNTAgent=NotFound')
    }

    if ([string]::IsNullOrWhiteSpace([string]$Service.PathName)) {
        Stop-WithResult \
            -Status 'AgentNotReady' \
            -Summary 'HUNTAgent has no executable path. Repair EDR before attempting Datto AV refresh.' \
            -Diagnostic @(("HUNTAgentState={0}" -f $Service.State))
    }

    $AgentPath = Get-AgentExecutablePath -ServicePath ([string]$Service.PathName)

    if ([string]::IsNullOrWhiteSpace($AgentPath)) {
        Stop-WithResult \
            -Status 'AgentPathInvalid' \
            -Summary 'Unable to parse the active HUNTAgent executable path.' \
            -Diagnostic @(("HUNTAgentPathName={0}" -f $Service.PathName))
    }

    try {
        $AgentPath = [System.IO.Path]::GetFullPath($AgentPath)
    }
    catch {
        Stop-WithResult \
            -Status 'AgentPathInvalid' \
            -Summary 'The active HUNTAgent executable path is invalid.' \
            -Diagnostic @(("ParsedAgentPath={0}" -f $AgentPath))
    }

    if (-not (Test-AllowedAgentPath -Path $AgentPath)) {
        Stop-WithResult \
            -Status 'UntrustedAgentPath' \
            -Summary 'HUNTAgent is running from an unapproved location; no AV command was executed.' \
            -Diagnostic @(("AgentPath={0}" -f $AgentPath))
    }

    if (-not (Test-Path -LiteralPath $AgentPath -PathType Leaf)) {
        Stop-WithResult \
            -Status 'AgentNotReady' \
            -Summary 'The active HUNTAgent executable is missing from disk.' \
            -Diagnostic @(("AgentPath={0}" -f $AgentPath))
    }

    if ([string]$Service.State -ne 'Running') {
        Stop-WithResult \
            -Status 'AgentNotReady' \
            -Summary 'HUNTAgent is not running. Repair EDR before attempting Datto AV refresh.' \
            -Diagnostic @(
                ("HUNTAgentState={0}" -f $Service.State),
                ("AgentPath={0}" -f $AgentPath)
            )
    }

    $Signature = Get-AuthenticodeSignature -LiteralPath $AgentPath

    if ($Signature.Status -ne 'Valid') {
        Stop-WithResult \
            -Status 'SignatureInvalid' \
            -Summary 'The active HUNTAgent executable does not have a valid Authenticode signature.' \
            -Diagnostic @(
                ("AgentPath={0}" -f $AgentPath),
                ("SignatureStatus={0}" -f $Signature.Status)
            )
    }

    $File = Get-Item -LiteralPath $AgentPath
    $FileVersion = [string]$File.VersionInfo.FileVersion
    $SignerSubject = if ($Signature.SignerCertificate) { [string]$Signature.SignerCertificate.Subject } else { 'Unknown' }

    $Existing = @(Get-ForceUpdateProcesses)

    if ($Existing.Count -gt 1) {
        Stop-WithResult \
            -Status 'MultipleUpdatesActive' \
            -Summary 'Multiple Datto AV force-update processes are already active; no new process was started.' \
            -Diagnostic @(
                ("AgentPath={0}" -f $AgentPath),
                ("ActiveForceUpdateCount={0}" -f $Existing.Count)
            )
    }

    $StartedNew = $false
    $StdOutPath = $null
    $StdErrPath = $null

    if ($Existing.Count -eq 1) {
        $ProcessId = [int]$Existing[0].ProcessId
        try {
            $Process = [System.Diagnostics.Process]::GetProcessById($ProcessId)
        }
        catch {
            $Process = $null
        }
    }
    else {
        $LogDirectory = Join-Path $env:ProgramData 'CentraStage\AEMAgent\Logs'
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null

        $Token = [guid]::NewGuid().ToString('N')
        $StdOutPath = Join-Path $LogDirectory ("Jason-DattoAVForceUpdate-{0}.stdout.log" -f $Token)
        $StdErrPath = Join-Path $LogDirectory ("Jason-DattoAVForceUpdate-{0}.stderr.log" -f $Token)

        $Process = Start-Process \
            -FilePath $AgentPath \
            -ArgumentList @('datto-av', '--force-update') \
            -PassThru \
            -WindowStyle Hidden \
            -RedirectStandardOutput $StdOutPath \
            -RedirectStandardError $StdErrPath

        $StartedNew = $true
    }

    if ($null -eq $Process) {
        Stop-WithResult \
            -Status 'ProcessLookupFailed' \
            -Summary 'The Datto AV force-update process could not be started or attached to.' \
            -Diagnostic @(("AgentPath={0}" -f $AgentPath))
    }

    $Deadline = (Get-Date).AddSeconds($MaxWaitSeconds)

    while ((Get-Date) -lt $Deadline) {
        try {
            $Process.Refresh()
            if ($Process.HasExited) {
                break
            }
        }
        catch {
            break
        }

        Start-Sleep -Seconds $PollSeconds
    }

    try {
        $Process.Refresh()
        $HasExited = $Process.HasExited
    }
    catch {
        $HasExited = $true
    }

    $Diagnostic = @(
        ("Component={0}" -f $ComponentName),
        ("HUNTAgentState={0}" -f $Service.State),
        ("AgentPath={0}" -f $AgentPath),
        ("AgentFileVersion={0}" -f $FileVersion),
        ("SignatureStatus={0}" -f $Signature.Status),
        ("SignerSubject={0}" -f $SignerSubject),
        ("ForceUpdatePID={0}" -f $Process.Id),
        ("StartedNewProcess={0}" -f $StartedNew)
    )

    if (-not $HasExited) {
        Write-ResultBlock \
            -Status 'PendingReboot' \
            -Summary 'Datto AV force-update is still active after the bounded wait. Do not redispatch; reboot and verify through the playbook.'
        Write-DiagnosticBlock -Lines ($Diagnostic + @(
            ("ObservedSeconds={0}" -f $MaxWaitSeconds),
            'RecommendedAction=Schedule the approved reboot, then rerun Check Datto EDR/AV Status.'
        ))
        exit 0
    }

    $ExitCode = $Process.ExitCode

    if ($StartedNew) {
        $StdOutLength = if ($StdOutPath -and (Test-Path -LiteralPath $StdOutPath)) { (Get-Item -LiteralPath $StdOutPath).Length } else { 0 }
        $StdErrLength = if ($StdErrPath -and (Test-Path -LiteralPath $StdErrPath)) { (Get-Item -LiteralPath $StdErrPath).Length } else { 0 }
        $Diagnostic += @(
            ("StdOutBytes={0}" -f $StdOutLength),
            ("StdErrBytes={0}" -f $StdErrLength)
        )
    }

    $Diagnostic += ("ExitCode={0}" -f $ExitCode)

    if ($ExitCode -eq 0) {
        Write-ResultBlock \
            -Status 'UpdateCommandCompleted' \
            -Summary 'Datto AV force-update command completed. Independent EDR/AV health verification is required.'
        Write-DiagnosticBlock -Lines $Diagnostic
        exit 0
    }

    Write-ResultBlock \
        -Status 'CommandFailed' \
        -Summary 'Datto AV force-update exited with a non-zero code. Do not redispatch automatically.'
    Write-DiagnosticBlock -Lines $Diagnostic
    exit 1
}
catch {
    Stop-WithResult \
        -Status 'ComponentError' \
        -Summary 'Datto AV force-update component encountered an unexpected error.' \
        -Diagnostic @(
            ("ExceptionType={0}" -f $_.Exception.GetType().FullName),
            ("ExceptionMessage={0}" -f $_.Exception.Message)
        )
}
