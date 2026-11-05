#requires -Version 5.1
<#
.SYNOPSIS
    AOT read-only sweep for remote-access trojans, unauthorized remote tools,
    persistence, unusual process execution, and endpoint security detections.
.DESCRIPTION
    Intended for Datto RMM Windows PowerShell 5.1 running as SYSTEM.
    Triage findings are NOT proof of compromise. Does not execute downloaded
    content, modify settings, terminate processes, quarantine, or remediate.
    V2: validate known signed security-service identities; record inactive Defender
    as optional coverage, not a false-positive collection error.
    Prints a bounded human summary first (useful with truncated MCP output),
    then compact structured JSON (maximum ~58,000 characters).
.PARAMETER MonitorMode
    Only when specified: exit 1 when High findings are present or a critical scan section fails.
    Otherwise successful collection exits 0 even if findings require review.
.PARAMETER DeepFileHunt
    Bounded search for hidden executable/script files in common writable
    locations, to help identify dormant droppers not currently running.
.PARAMETER ApprovedRemoteTools
    Names known to be authorized in the environment. Matching tools remain
    visible as inventory; this setting never suppresses risk signals.
.EXAMPLE
    .\AOT-Hidden-RAT-Threat-Sweep-ReadOnly.ps1
.EXAMPLE
    .\AOT-Hidden-RAT-Threat-Sweep-ReadOnly.ps1 -MonitorMode -ApprovedRemoteTools 'Datto','Splashtop'
.NOTES
    No administrator confirmation or interactive prompts. Windows Security,
    user-mode APIs, and the loaded registry hives cannot detect every rootkit,
    injected process, offline-user persistence, or fileless implant.
#>
[CmdletBinding()]
param(
    [ValidateRange(1,180)][int]$RecentDays = 30,
    [ValidateRange(20,200)][int]$MaxFindings = 90,
    [switch]$MonitorMode,
    [switch]$DeepFileHunt,
    [string[]]$ApprovedRemoteTools = @()
)

$ErrorActionPreference = 'Stop'
$script:StartedAt = Get-Date
$script:Findings = New-Object 'System.Collections.Generic.List[object]'
$script:CollectionProblems = New-Object 'System.Collections.Generic.List[object]'
$script:Seen = @{}
$script:FileCache = @{}
$script:OmittedFindings = 0
$script:SignaturesChecked = 0
$script:HashesChecked = 0
$script:Stats = [ordered]@{
    processes = 0; process_paths_unavailable = 0; established_tcp = 0; services = 0; scheduled_tasks = 0
    autorun_values = 0; startup_files = 0; wmi_consumers = 0
    installed_programs = 0; defender_detections = 0; candidate_files = 0
    expected_signed_security_components = 0
}

$script:RemoteToolRegex = '(?i)(anydesk|rustdesk|teamviewer|screenconnect|connectwise[ ._-]*control|dwagent|meshagent|splashtop|ateraagent|remoteutilities|ammyy|ultravnc|tightvnc|vncserver|radmin|logmein|zohoassist|netsupport|ngrok|cloudflared|chisel|frpc|tacticalrmm|simplehelp)'
$script:MalwareToolRegex = '(?i)(mimikatz|lazagne|sharphound|bloodhound|rubeus|psexecsvc|remcos|asyncrat|quasar(?:rat)?|njrat|nanocore|darkcomet|poisonivy|xworm|warzone[ ._-]*rat|revenge[ ._-]*rat)'
$script:MasqueradeRegex = '(?i)^(svchost|lsass|services|winlogon|csrss|smss|spoolsv|taskhostw)\.exe$'
$script:OptionalSections = New-Object 'System.Collections.Generic.List[object]'
$script:DefenderCoverage = [ordered]@{
    antivirus_status = 'unknown'; preferences_status = 'not_checked'
    detection_status = 'not_checked'; preferences_reason = ''
}

function Add-Problem {
    param([string]$Section, [object]$ErrorRecord)
    $typeName = 'Unavailable'
    $errorCode = ''
    if ($null -ne $ErrorRecord -and $null -ne $ErrorRecord.Exception) {
        $typeName = $ErrorRecord.Exception.GetType().Name
        $exception = $ErrorRecord.Exception
        # Provider HRESULT is safe to report; avoid printing exception messages,
        # which could contain file paths, user data or tokens.
        if ($null -ne $exception.HResult -and $exception.HResult -ne 0) {
            $errorCode = ('0x{0:X8}' -f ([uint32]([int64]$exception.HResult -band 0xFFFFFFFFL)))
        }
        if ([string]$ErrorRecord.FullyQualifiedErrorId -match '(?i)0x[0-9a-f]{8}') {
            $errorCode = [string]$Matches[0]
        }
    }
    $script:CollectionProblems.Add([pscustomobject]@{
        section = $Section; error_type = $typeName; error_code = $errorCode
    })
}
function Add-OptionalSection {
    param([string]$Section, [string]$Status, [string]$Reason)
    $script:OptionalSections.Add([pscustomobject]@{
        section = $Section; status = $Status; reason = $Reason
    })
}
function Short-Text {
    param([object]$Value, [int]$Limit = 180)
    if ($null -eq $Value) { return '' }
    $text = [string]$Value
    $text = $text.Replace("`r", ' ').Replace("`n", ' ').Replace("`t", ' ')
    if ($text.Length -gt $Limit) { return $text.Substring(0, $Limit) }
    return $text
}
function Get-Signals {
    param([string]$Command)
    $signals = New-Object 'System.Collections.Generic.List[string]'
    if ([string]::IsNullOrWhiteSpace($Command)) { return @() }
    if ($Command -match '(?i)(?:^|\s)-(?:e|enc|encodedcommand)\s+[A-Za-z0-9+/=]{12,}') { $signals.Add('EncodedPowerShell') }
    if ($Command -match '(?i)(frombase64string\s*\(|downloadstring\s*\(|invoke-expression\b|\biex\s*\()') { $signals.Add('DecodeOrExecute') }
    if ($Command -match '(?i)(mshta(?:\.exe)?\s+https?://|regsvr32.+(?:scrobj\.dll|/i:https?://)|rundll32.+https?://)') { $signals.Add('RemoteScriptExecution') }
    if ($Command -match '(?i)(certutil(?:\.exe)?\s+.+-(?:urlcache|decode)\b|bitsadmin(?:\.exe)?\s+.+/transfer\b)') { $signals.Add('LOLBINTransfer') }
    if ($Command -match '(?i)(add-mppreference.+-exclusionpath|set-mppreference.+-disablerealtimemonitoring)') { $signals.Add('DefenderChangeCommand') }
    if ($Command -match '(?i)(-windowstyle\s+hidden|\s-w\s+hidden\b|\s-nop\s+.*-enc\b)') { $signals.Add('ConcealedPowerShell') }
    return @($signals.ToArray())
}
function Get-ExecutablePath {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($Command)) { return '' }
    $value = [Environment]::ExpandEnvironmentVariables($Command.Trim())
    if ($value -match '^"([^"]+\.(?:exe|dll|ps1|vbs|js|bat|cmd|hta))"') { return $Matches[1] }
    if ($value -match '^([A-Za-z]:\\.+?\.(?:exe|dll|ps1|vbs|js|bat|cmd|hta))(?=\s|$)') { return $Matches[1] }
    if ($value -match '^([^\s"]+\.(?:exe|dll|ps1|vbs|js|bat|cmd|hta))(?=\s|$)') { return $Matches[1] }
    # Path parsing is a best-effort hint, not evidence of file execution.
    return ''
}
function Get-PathClass {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    if ($Path -match '(?i)(\\AppData\\Local\\Temp\\|\\Windows\\Temp\\|\\Users\\Public\\|\\\$Recycle\.Bin\\|\\Downloads\\)') { return 'HighRiskWritableLocation' }
    if ($Path -match '(?i)(\\AppData\\|\\ProgramData\\|\\PerfLogs\\)') { return 'UserWritableLocation' }
    return ''
}
function Is-ApprovedRemoteTool {
    param([string]$Tool)
    foreach ($item in @($ApprovedRemoteTools)) {
        if ([string]::IsNullOrWhiteSpace($item)) { continue }
        if ($Tool.IndexOf($item, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}
function Get-FileFacts {
    param([string]$Path, [bool]$Hash = $false)
    $facts = [ordered]@{ exists = $false; signature = 'not_checked'; signer_subject = ''; hidden = $false; sha256 = '' }
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:\\') { return [pscustomobject]$facts }
    $key = $Path.ToLowerInvariant()
    if ($script:FileCache.ContainsKey($key)) {
        $prior = $script:FileCache[$key]
        if (-not $Hash -or $prior.sha256) { return $prior }
    }
    try {
        $file = Get-Item -LiteralPath $Path -ErrorAction Stop
        if ($file.PSIsContainer) { return [pscustomobject]$facts }
        $facts.exists = $true
        $facts.hidden = (($file.Attributes -band [IO.FileAttributes]::Hidden) -ne 0)
        if ($script:SignaturesChecked -lt 100) {
            $script:SignaturesChecked++
            try {
                $sig = Get-AuthenticodeSignature -LiteralPath $Path -ErrorAction Stop
                $facts.signature = [string]$sig.Status
                if ($null -ne $sig.SignerCertificate) {
                    $facts.signer_subject = [string]$sig.SignerCertificate.Subject
                }
            } catch { $facts.signature = 'unavailable' }
        }
        if ($Hash -and $file.Length -le 52428800 -and $script:HashesChecked -lt 12) {
            $script:HashesChecked++
            try { $facts.sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant() } catch { }
        }
    } catch { }
    $obj = [pscustomobject]$facts
    $script:FileCache[$key] = $obj
    return $obj
}
# Suppress *heuristic location-only escalation* for known security components,
# but retain each item as informational inventory. Name or location alone NEVER
# provides trust: require a valid Authenticode signature, an expected signer,
# exact service/autorun name, expected binary name and narrow installation path.
# Malicious command-line signals, executable masquerading and independent RAT
# matches are unaffected by this function.
function Get-ExpectedSignedSecurityComponent {
    param([string]$Kind, [string]$Name, [string]$Path, [string[]]$Signals = @())
    if ([string]::IsNullOrWhiteSpace($Path) -or @($Signals).Count -gt 0) { return '' }
    if ((Get-PathClass $Path) -eq 'HighRiskWritableLocation') { return '' }
    $facts = Get-FileFacts -Path $Path
    if ($facts.signature -ne 'Valid' -or $facts.hidden -or -not $facts.exists) { return '' }
    $ms = ($facts.signer_subject -match '(?i)O=Microsoft Corporation')
    $vendor = ($facts.signer_subject -match '(?i)(Datto|Kaseya|CentraStage|Bitdefender|Avira|Gen Digital|NortonLifeLock)')
    if ($Kind -eq 'Service' -and $ms -and $Path -match '(?i)^[A-Za-z]:\\ProgramData\\Microsoft\\Windows Defender\\Platform\\[^\\]+\\(MsMpEng|NisSrv|MpDefenderCoreService)\.exe$') {
        if (($Name -eq 'WinDefend' -and $Path -match '(?i)\\MsMpEng\.exe$') -or
            ($Name -eq 'WdNisSvc' -and $Path -match '(?i)\\NisSrv\.exe$') -or
            ($Name -eq 'MDCoreSvc' -and $Path -match '(?i)\\MpDefenderCoreService\.exe$')) {
            return 'ExpectedSignedMicrosoftDefenderService'
        }
    }
    if (($Kind -eq 'Service' -or $Kind -eq 'RegistryAutorun') -and $vendor -and
        $Path -match '(?i)^[A-Za-z]:\\ProgramData\\CentraStage\\AEMAgent\\[^\\]+\\' -and
        ($Name -match '(?i)(Datto|EndpointProtection|AdvancedThreatDetection)' -or
         $Path -match '(?i)\\dattoav\\')) {
        return 'ExpectedSignedAOTSecurityComponent'
    }
    return ''
}
function Add-Finding {
    param(
        [ValidateSet('High','Medium','Low','Info')][string]$Severity,
        [string]$Category, [string]$Title, [string]$Name = '',
        [string]$Path = '', [string[]]$Signals = @(),
        [int]$ProcessId = 0, [string]$Remote = '',
        [bool]$IncludeHash = $false
    )
    $identifier = ($Category + '|' + $Title + '|' + $Name + '|' + $Path + '|' + $ProcessId).ToLowerInvariant()
    if ($script:Seen.ContainsKey($identifier)) { return }
    $script:Seen[$identifier] = $true
    if ($script:Findings.Count -ge 4000) { $script:OmittedFindings++; return }
    $facts = Get-FileFacts -Path $Path -Hash $IncludeHash
    $script:Findings.Add([pscustomobject][ordered]@{
        severity = $Severity; category = (Short-Text $Category 40)
        title = (Short-Text $Title 110); name = (Short-Text $Name 120)
        path = (Short-Text $Path 240); pid = $ProcessId
        signals = @($Signals | Select-Object -Unique)
        remote = (Short-Text $Remote 90)
        exists = $facts.exists; signature = $facts.signature
        hidden_attribute = $facts.hidden; sha256 = $facts.sha256
    })
}

# Network connections are read first so process findings can be correlated.
$tcpByPid = @{}
try {
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $connections = @(Get-NetTCPConnection -State Established -ErrorAction Stop | Select-Object -First 2000)
        $script:Stats['established_tcp'] = $connections.Count
        foreach ($connection in $connections) {
            $pidKey = [string]$connection.OwningProcess
            $remoteIP = [string]$connection.RemoteAddress
            if ($remoteIP -eq '127.0.0.1' -or $remoteIP -eq '::1' -or $remoteIP -eq '0.0.0.0' -or $remoteIP -eq '::') { continue }
            if (-not $tcpByPid.ContainsKey($pidKey)) { $tcpByPid[$pidKey] = New-Object 'System.Collections.Generic.List[string]' }
            if ($tcpByPid[$pidKey].Count -lt 3) {
                $tcpByPid[$pidKey].Add((Short-Text ($remoteIP + ':' + $connection.RemotePort) 90))
            }
        }
    } else { Add-Problem 'TCP' $null }
} catch { Add-Problem 'TCP' $_ }

# Running processes (bounded first-pass Win32 inventory).
try {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop | Select-Object -First 2000)
    $script:Stats['processes'] = $processes.Count
    foreach ($proc in $processes) {
        $name = [string]$proc.Name
        $path = [string]$proc.ExecutablePath
        $cmd = [string]$proc.CommandLine # inspected in memory only; NEVER printed
        $pidNumber = [int]$proc.ProcessId
        $signals = @(Get-Signals $cmd)
        $class = Get-PathClass $path
        $ratName = ($name -match $script:MalwareToolRegex -or $path -match $script:MalwareToolRegex)
        $toolName = ($name -match $script:RemoteToolRegex -or $path -match $script:RemoteToolRegex)
        # A null/blank Win32_Process.ExecutablePath is unknown, NOT evidence of
        # masquerading. Protected system processes may legitimately hide paths
        # from CIM even when the collector runs as SYSTEM.
        if ([string]::IsNullOrWhiteSpace($path)) {
            $script:Stats['process_paths_unavailable']++
        }
        $masquerade = (-not [string]::IsNullOrWhiteSpace($path) -and
            $name -match $script:MasqueradeRegex -and
            $path -notmatch '(?i)^[A-Za-z]:\\Windows\\(System32|SysWOW64)\\')
        $connections = @()
        if ($tcpByPid.ContainsKey([string]$pidNumber)) { $connections = @($tcpByPid[[string]$pidNumber].ToArray()) }
        $remoteSample = ($connections | Select-Object -First 2) -join ', '
        if ($ratName) {
            Add-Finding -Severity High -Category Process -Title 'Known offensive/RAT-style tool name (verify identity)' -Name $name -Path $path -ProcessId $pidNumber -Remote $remoteSample -Signals $signals -IncludeHash $true
        } elseif ($masquerade) {
            Add-Finding -Severity High -Category Process -Title 'Windows system-process name outside expected Windows directory' -Name $name -Path $path -ProcessId $pidNumber -Remote $remoteSample -Signals $signals -IncludeHash $true
        }
        if ($signals.Count -gt 0) {
            $level = 'Medium'
            if ($signals -contains 'EncodedPowerShell' -or $signals -contains 'RemoteScriptExecution' -or $signals -contains 'DefenderChangeCommand') { $level = 'High' }
            Add-Finding -Severity $level -Category CommandBehavior -Title 'Suspicious command-execution pattern' -Name $name -Path $path -ProcessId $pidNumber -Remote $remoteSample -Signals $signals -IncludeHash ($level -eq 'High')
        }
        if ($toolName) {
            $title = 'Remote-access/tunnel tool observed (authorization review)'
            if (Is-ApprovedRemoteTool ($name + ' ' + $path)) { $title = 'Approved-list remote-support tool observed (inventory)' }
            Add-Finding -Severity Info -Category RemoteTool -Title $title -Name $name -Path $path -ProcessId $pidNumber -Remote $remoteSample
        }
        if ($class -and $connections.Count -gt 0 -and -not $ratName -and -not $masquerade) {
            $facts = Get-FileFacts -Path $path
            if ($facts.signature -ne 'Valid') {
                $level = 'Medium'
                if ($class -eq 'HighRiskWritableLocation' -and $facts.hidden) { $level = 'High' }
                Add-Finding -Severity $level -Category ProcessNetwork -Title 'Non-validly-signed process in writable location has TCP connection' -Name $name -Path $path -ProcessId $pidNumber -Remote $remoteSample -Signals @($class) -IncludeHash ($level -eq 'High')
            }
        }
    }
} catch { Add-Problem 'Processes' $_ }

# Services: persistent program entry points; do not restart or query status changes.
try {
    $services = @(Get-CimInstance Win32_Service -ErrorAction Stop | Select-Object -First 1800)
    $script:Stats['services'] = $services.Count
    foreach ($svc in $services) {
        $cmd = [string]$svc.PathName
        $path = Get-ExecutablePath $cmd
        $context = [string]$svc.Name + ' ' + [string]$svc.DisplayName + ' ' + $path
        $riskClass = Get-PathClass $path
        $signals = @(Get-Signals $cmd)
        if ($context -match $script:MalwareToolRegex) {
            Add-Finding -Severity High -Category Service -Title 'Persistent service resembles known offensive/RAT tool' -Name $svc.Name -Path $path -Signals $signals -IncludeHash $true
        } elseif ($riskClass -or $signals.Count -gt 0) {
            $expected = Get-ExpectedSignedSecurityComponent -Kind 'Service' -Name ([string]$svc.Name) -Path $path -Signals $signals
            if ($expected) {
                $script:Stats['expected_signed_security_components']++
                Add-Finding -Severity Info -Category SecurityComponent -Title 'Expected signed security service (inventory; verify authorization)' -Name $svc.Name -Path $path -Signals @($expected)
            } else {
                $severity = 'Medium'
                if ($riskClass -eq 'HighRiskWritableLocation' -and $signals.Count -gt 0) { $severity = 'High' }
                Add-Finding -Severity $severity -Category Service -Title 'Persistent service in writable location or suspicious command' -Name $svc.Name -Path $path -Signals (@($riskClass) + $signals) -IncludeHash ($severity -eq 'High')
            }
        }
        if ($context -match $script:RemoteToolRegex) {
            Add-Finding -Severity Info -Category RemoteTool -Title 'Installed remote-support service (authorization review)' -Name $svc.Name -Path $path
        }
    }
} catch { Add-Problem 'Services' $_ }

# Scheduled tasks: inspect action metadata only, never invoke task actions.
try {
    if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
        $tasks = @(Get-ScheduledTask -ErrorAction Stop | Select-Object -First 1800)
        $script:Stats['scheduled_tasks'] = $tasks.Count
        foreach ($task in $tasks) {
            foreach ($action in @($task.Actions)) {
                if (-not $action.Execute) { continue }
                $path = [Environment]::ExpandEnvironmentVariables([string]$action.Execute)
                $cmd = $path + ' ' + [string]$action.Arguments
                $signals = @(Get-Signals $cmd)
                $riskClass = Get-PathClass $path
                $context = [string]$task.TaskName + ' ' + $path
                if ($context -match $script:MalwareToolRegex) {
                    Add-Finding -Severity High -Category ScheduledTask -Title 'Scheduled task resembles known offensive/RAT tool' -Name $task.TaskName -Path $path -Signals $signals -IncludeHash $true
                } elseif ($riskClass -or $signals.Count -gt 0) {
                    $level = 'Medium'
                    if ($signals -contains 'EncodedPowerShell' -or $signals -contains 'RemoteScriptExecution') { $level = 'High' }
                    Add-Finding -Severity $level -Category ScheduledTask -Title 'Scheduled persistence using writable path or suspicious arguments' -Name $task.TaskName -Path $path -Signals (@($riskClass) + $signals) -IncludeHash ($level -eq 'High')
                }
            }
        }
    } else { Add-Problem 'ScheduledTasks' $null }
} catch { Add-Problem 'ScheduledTasks' $_ }

# HKLM and loaded HKU user Run keys. Offline NTUSER.DAT hives are not mounted.
$autorunKeys = @(
    'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
    'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce',
    'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run',
    'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run'
)
try {
    foreach ($hive in @(Get-ChildItem 'Registry::HKEY_USERS' -ErrorAction Stop)) {
        if ($hive.PSChildName -match '^S-1-5-21-\d+-\d+-\d+-\d+$') {
            foreach ($suffix in @('Software\Microsoft\Windows\CurrentVersion\Run','Software\Microsoft\Windows\CurrentVersion\RunOnce','Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run')) {
                $autorunKeys += ('Registry::HKEY_USERS\' + $hive.PSChildName + '\' + $suffix)
            }
        }
    }
} catch { Add-Problem 'LoadedUserHives' $_ }
foreach ($key in $autorunKeys) {
    try {
        if (-not (Test-Path -LiteralPath $key)) { continue }
        $record = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
        foreach ($entry in $record.PSObject.Properties) {
            if ($entry.Name -match '^PS(Path|ParentPath|ChildName|Drive|Provider)$') { continue }
            $script:Stats['autorun_values']++
            $cmd = [string]$entry.Value
            $path = Get-ExecutablePath $cmd
            $signals = @(Get-Signals $cmd)
            $risk = Get-PathClass $path
            $context = [string]$entry.Name + ' ' + $path
            $entryName = (Short-Text ($entry.Name + ' @ ' + $key) 120)
            if ($context -match $script:MalwareToolRegex) {
                Add-Finding -Severity High -Category RegistryAutorun -Title 'Autorun resembles known offensive/RAT tool' -Name $entryName -Path $path -Signals $signals -IncludeHash $true
            } elseif ($risk -or $signals.Count -gt 0) {
                $expected = Get-ExpectedSignedSecurityComponent -Kind 'RegistryAutorun' -Name ([string]$entry.Name) -Path $path -Signals $signals
                if ($expected) {
                    $script:Stats['expected_signed_security_components']++
                    Add-Finding -Severity Info -Category SecurityComponent -Title 'Expected signed AOT security autorun (inventory; verify authorization)' -Name $entryName -Path $path -Signals @($expected)
                } else {
                    $level = 'Medium'
                    if ($signals -contains 'EncodedPowerShell' -or $signals -contains 'RemoteScriptExecution') { $level = 'High' }
                    Add-Finding -Severity $level -Category RegistryAutorun -Title 'Autorun executes from writable path or has suspicious arguments' -Name $entryName -Path $path -Signals (@($risk) + $signals) -IncludeHash ($level -eq 'High')
                }
            }
        }
    } catch { Add-Problem 'RegistryAutoruns' $_ }
}

# Registry hijacks: unusual Winlogon Shell/Userinit, IFEO Debugger values.
try {
    $key = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    $w = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
    if ([string]$w.Shell -and ([string]$w.Shell).Trim() -ine 'explorer.exe') {
        Add-Finding -Severity High -Category RegistryHijack -Title 'Nonstandard Winlogon Shell requires review' -Name 'Winlogon Shell' -Path (Get-ExecutablePath ([string]$w.Shell))
    }
    $userinit = ([string]$w.Userinit).Trim().TrimEnd(',')
    if ($userinit -and $userinit -notmatch '(?i)^([A-Za-z]:\\Windows\\System32\\)?userinit\.exe$') {
        Add-Finding -Severity High -Category RegistryHijack -Title 'Nonstandard Winlogon Userinit requires review' -Name 'Winlogon Userinit' -Path (Get-ExecutablePath ([string]$w.Userinit))
    }
} catch { Add-Problem 'Winlogon' $_ }
try {
    $key = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options'
    foreach ($item in @(Get-ChildItem -LiteralPath $key -ErrorAction Stop | Select-Object -First 500)) {
        try {
            $v = Get-ItemProperty -LiteralPath $item.PSPath -Name Debugger -ErrorAction Stop
            if ([string]$v.Debugger) {
                $path = Get-ExecutablePath ([string]$v.Debugger)
                Add-Finding -Severity Medium -Category RegistryHijack -Title 'Image File Execution Options Debugger persistence' -Name $item.PSChildName -Path $path -Signals @(Get-Signals ([string]$v.Debugger))
            }
        } catch { } # No Debugger value is normal; do not report an error per key.
    }
} catch { Add-Problem 'IFEO' $_ }

# WMI permanent event consumers are uncommon and merit inspection.
try {
    foreach ($class in @('CommandLineEventConsumer','ActiveScriptEventConsumer')) {
        foreach ($consumer in @(Get-CimInstance -Namespace root/subscription -ClassName $class -ErrorAction Stop | Select-Object -First 100)) {
            $script:Stats['wmi_consumers']++
            $name = [string]$consumer.Name
            $cmd = [string]$consumer.CommandLineTemplate
            if (-not $cmd) { $cmd = [string]$consumer.ExecutablePath }
            $path = Get-ExecutablePath $cmd
            $signals = @(Get-Signals $cmd)
            $level = 'Medium'
            if ($signals.Count -gt 0 -or (Get-PathClass $path) -eq 'HighRiskWritableLocation') { $level = 'High' }
            Add-Finding -Severity $level -Category WMIPersistence -Title ('Permanent WMI event consumer: ' + $class) -Name $name -Path $path -Signals $signals -IncludeHash ($level -eq 'High')
        }
    }
} catch { Add-Problem 'WMIEventConsumers' $_ }

# Common and profile startup folders (filenames only; never open/execute shortcuts).
$startupFolders = @()
try {
    $common = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Startup'
    $startupFolders += $common
    $profilesKey = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList'
    foreach ($profileReg in @(Get-ChildItem -LiteralPath $profilesKey -ErrorAction Stop | Select-Object -First 100)) {
        try {
            $profile = (Get-ItemProperty -LiteralPath $profileReg.PSPath -Name ProfileImagePath -ErrorAction Stop).ProfileImagePath
            $profile = [Environment]::ExpandEnvironmentVariables([string]$profile)
            if ($profile -match '^[A-Za-z]:\\') {
                $startupFolders += (Join-Path $profile 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup')
            }
        } catch { }
    }
    foreach ($folder in @($startupFolders | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $folder -PathType Container)) { continue }
        foreach ($file in @(Get-ChildItem -LiteralPath $folder -File -ErrorAction Stop | Select-Object -First 70)) {
            $script:Stats['startup_files']++
            if ($file.Extension -notmatch '(?i)^\.(exe|dll|ps1|vbs|js|wsf|hta|bat|cmd|lnk)$') { continue }
            $level = 'Low'
            if ($file.Name -match $script:MalwareToolRegex -or $file.Extension -match '(?i)^\.(vbs|js|wsf|hta)$') { $level = 'Medium' }
            Add-Finding -Severity $level -Category StartupFolder -Title 'Executable/script/shortcut placed in automatic startup' -Name $file.Name -Path $file.FullName -IncludeHash ($level -eq 'Medium')
        }
    }
} catch { Add-Problem 'StartupFolders' $_ }

# Installed applications: inventory potentially legitimate remote-support software.
try {
    $uninstallKeys = @(
        'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($parent in $uninstallKeys) {
        foreach ($item in @(Get-ChildItem -LiteralPath $parent -ErrorAction Stop | Select-Object -First 1000)) {
            try {
                $app = Get-ItemProperty -LiteralPath $item.PSPath -ErrorAction Stop
                if (-not $app.DisplayName) { continue }
                $script:Stats['installed_programs']++
                $display = [string]$app.DisplayName
                if ($display -match $script:RemoteToolRegex) {
                    $title = 'Remote-support software installed (authorization review)'
                    if (Is-ApprovedRemoteTool $display) { $title = 'Approved-list remote-support software installed (inventory)' }
                    Add-Finding -Severity Info -Category InstalledRemoteTool -Title $title -Name $display
                }
                if ($display -match $script:MalwareToolRegex) {
                    Add-Finding -Severity High -Category InstalledOffensiveTool -Title 'Installed program resembles offensive/RAT tool' -Name $display
                }
            } catch { }
        }
    }
} catch { Add-Problem 'InstalledPrograms' $_ }

# Optional bounded dormant-file hunt. No full-drive walk or file execution.
if ($DeepFileHunt) {
    $huntRoots = @(
        (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'),
        (Join-Path $env:ProgramData 'Microsoft\Windows\Caches'),
        (Join-Path $env:ProgramData 'Microsoft\Windows\Temp'),
        (Join-Path $env:SystemRoot 'Temp'),
        (Join-Path $env:PUBLIC 'Downloads')
    )
    $huntRoots += $env:PUBLIC
    try {
        $profilesKey = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList'
        foreach ($profileReg in @(Get-ChildItem -LiteralPath $profilesKey -ErrorAction Stop | Select-Object -First 20)) {
            try {
                $profile = [Environment]::ExpandEnvironmentVariables([string](Get-ItemProperty -LiteralPath $profileReg.PSPath -Name ProfileImagePath -ErrorAction Stop).ProfileImagePath)
                if ($profile -match '^[A-Za-z]:\\') {
                    $huntRoots += (Join-Path $profile 'AppData\Local\Temp')
                    $huntRoots += (Join-Path $profile 'AppData\Roaming')
                }
            } catch { }
        }
    } catch { Add-Problem 'HiddenFileRoots' $_ }
    $totalInspected = 0
    foreach ($root in @($huntRoots | Select-Object -Unique)) {
        if ($totalInspected -ge 6000) { break }
        if ([string]::IsNullOrWhiteSpace($root) -or -not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        try {
            $files = @(Get-ChildItem -LiteralPath $root -Force -File -Recurse -Depth 2 -ErrorAction SilentlyContinue | Select-Object -First 700)
            foreach ($file in $files) {
                if ($totalInspected -ge 6000) { break }
                $totalInspected++
                if ($file.Extension -notmatch '(?i)^\.(exe|dll|scr|ps1|vbs|js|wsf|hta|bat|cmd)$') { continue }
                $script:Stats['candidate_files']++
                $isHidden = (($file.Attributes -band [IO.FileAttributes]::Hidden) -ne 0)
                $isMalwareStyle = ($file.Name -match $script:MalwareToolRegex)
                $isMasquerade = ($file.Name -match $script:MasqueradeRegex)
                if (-not ($isHidden -or $isMalwareStyle -or $isMasquerade)) { continue }
                $severity = 'Low'
                $title = 'Hidden executable/script in writable location (review)'
                if ($isMalwareStyle -or $isMasquerade) {
                    $severity = 'High'
                    $title = 'Suspicious executable/tool name found at rest'
                } elseif ($file.Extension -match '(?i)^\.(exe|dll|scr)$') {
                    $facts = Get-FileFacts -Path $file.FullName
                    if ($facts.signature -ne 'Valid') { $severity = 'Medium' }
                }
                Add-Finding -Severity $severity -Category DormantFile -Title $title -Name $file.Name -Path $file.FullName -Signals @('BoundedDepth2','NoExecution') -IncludeHash ($severity -eq 'High')
            }
        } catch { Add-Problem 'HiddenFileHunt' $_ }
    }
}

# Defender telemetry is optional when Datto AV or another product is primary.
# An inactive Defender engine produces 0x800106ba from Get-MpPreference; this
# is an explicitly reported coverage limitation, not a scan-wide failure.
try {
    if (Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue) {
        $mp = Get-MpComputerStatus -ErrorAction Stop
        $mode = [string]$mp.AMRunningMode
        $script:DefenderCoverage['antivirus_status'] = 'unknown'
        if ($mode -eq 'Not running' -or $mp.AntivirusEnabled -eq $false) {
            $script:DefenderCoverage['antivirus_status'] = 'inactive'
        } elseif ($mode) {
            $script:DefenderCoverage['antivirus_status'] = 'active_or_passive'
        }
    }
} catch {
    $script:DefenderCoverage['antivirus_status'] = 'unknown'
    Add-OptionalSection 'DefenderStatus' 'unavailable' 'Microsoft Defender status query unavailable'
}
try {
    if (Get-Command Get-MpThreatDetection -ErrorAction SilentlyContinue) {
        $cutoff = (Get-Date).AddDays(-$RecentDays)
        foreach ($threat in @(Get-MpThreatDetection -ErrorAction Stop | Select-Object -First 150)) {
            $detected = $null
            try { $detected = [datetime]$threat.InitialDetectionTime } catch { }
            if ($null -ne $detected -and $detected -lt $cutoff) { continue }
            $script:Stats['defender_detections']++
            $threatLabel = [string]$threat.ThreatName
            if (-not $threatLabel) { $threatLabel = 'ThreatID ' + [string]$threat.ThreatID }
            Add-Finding -Severity High -Category Defender -Title 'Recent Microsoft Defender threat detection: verify remediation' -Name $threatLabel
        }
        $script:DefenderCoverage['detection_status'] = 'collected'
    } else {
        $script:DefenderCoverage['detection_status'] = 'unavailable'
        Add-OptionalSection 'DefenderDetection' 'unavailable' 'Defender detection cmdlet is unavailable'
    }
} catch {
    $script:DefenderCoverage['detection_status'] = 'unavailable'
    Add-Problem 'DefenderDetection' $_
}
if ($script:DefenderCoverage['antivirus_status'] -eq 'inactive') {
    $script:DefenderCoverage['preferences_status'] = 'skipped_inactive'
    $script:DefenderCoverage['preferences_reason'] = 'Defender antivirus not running; third-party AV may be primary'
    Add-OptionalSection 'DefenderPreference' 'skipped_inactive' 'Microsoft Defender antivirus not running; exclusions not verified'
} else {
    try {
        if (Get-Command Get-MpPreference -ErrorAction SilentlyContinue) {
            $pref = Get-MpPreference -ErrorAction Stop
            foreach ($path in @($pref.ExclusionPath)) {
                if ($path -match '(?i)^(?:[A-Za-z]:\\(?:\*|$)|[A-Za-z]:\\Users\\\*|[A-Za-z]:\\Windows\\\*|[A-Za-z]:\\ProgramData\\\*)$') {
                    Add-Finding -Severity Medium -Category DefenderConfiguration -Title 'Broad Defender path exclusion warrants review' -Name 'ExclusionPath' -Path ([string]$path)
                }
            }
            $script:DefenderCoverage['preferences_status'] = 'collected'
        } else {
            $script:DefenderCoverage['preferences_status'] = 'unavailable'
            $script:DefenderCoverage['preferences_reason'] = 'Defender preference cmdlet is unavailable'
            Add-OptionalSection 'DefenderPreference' 'unavailable' 'Defender preference cmdlet is unavailable'
        }
    } catch {
        $exceptionMessage = [string]$_.Exception.Message
        $fqid = [string]$_.FullyQualifiedErrorId
        if ($exceptionMessage -match '0x800106ba' -or $fqid -match '0x800106ba') {
            $script:DefenderCoverage['preferences_status'] = 'skipped_inactive'
            $script:DefenderCoverage['preferences_reason'] = 'Defender engine unavailable (0x800106ba)'
            Add-OptionalSection 'DefenderPreference' 'skipped_inactive' 'Defender engine unavailable (0x800106ba); exclusions not verified'
        } else {
            $script:DefenderCoverage['preferences_status'] = 'error'
            $script:DefenderCoverage['preferences_reason'] = 'Unexpected Defender preference collection error'
            Add-Problem 'DefenderPreference' $_
        }
    }
}

# Higher-priority findings appear first, followed by bounded structured detail.
$severityOrder = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
$allSorted = @($script:Findings.ToArray() | Sort-Object @{ Expression = { $severityOrder[$_.severity] } }, category, title)
$sorted = @($allSorted | Select-Object -First $MaxFindings)
$script:OmittedFindings += [Math]::Max(0, $allSorted.Count - $sorted.Count)
$counts = [ordered]@{ High = 0; Medium = 0; Low = 0; Info = 0 }
foreach ($f in $allSorted) { $counts[$f.severity]++ }
$overallStatus = 'complete'
if ($script:CollectionProblems.Count -gt 0) { $overallStatus = 'partial' }
$summary = [ordered]@{
    high = $counts['High']; medium = $counts['Medium']; low = $counts['Low']; info = $counts['Info']
    recorded_findings = $sorted.Count; omitted_findings = $script:OmittedFindings
    sections_with_errors = $script:CollectionProblems.Count
}
$report = [ordered]@{
    schema_version = '1.0'; collector = 'AOT-Hidden-RAT-Threat-Sweep'; read_only = $true
    computer = $env:COMPUTERNAME; collected_utc = (Get-Date).ToUniversalTime().ToString('o')
    execution_identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    collection_status = $overallStatus; deep_file_hunt = [bool]$DeepFileHunt; summary = $summary; scanned = $script:Stats
    findings = @($sorted); collection_errors = @($script:CollectionProblems.ToArray())
    optional_sections = @($script:OptionalSections.ToArray()); defender_coverage = $script:DefenderCoverage
    limitations = @('Heuristic findings require review; authorized remote-support tools may appear.',
       'An inactive or unavailable Microsoft Defender sensor does not establish that Datto AV or another product is healthy.',
       'Does not prove absence of malware, kernel rootkits, injection, or memory-only implants.',
       'Does not mount offline user registry hives or scan every file on disk.',
       'Optional DeepFileHunt is depth/volume bounded and does not scan all executable files.',
       'Raw command lines are analyzed but never included in output to avoid credential exposure.')
    output_bounded = $false
}
$json = ConvertTo-Json -InputObject $report -Compress -Depth 7
while ($json.Length -gt 56000 -and @($report['findings']).Count -gt 0) {
    $report['findings'] = @($report['findings'] | Select-Object -SkipLast 1)
    $report['summary']['omitted_findings']++
    $report['output_bounded'] = $true
    $json = ConvertTo-Json -InputObject $report -Compress -Depth 7
}
$seconds = [math]::Round(((Get-Date) - $script:StartedAt).TotalSeconds, 1)
Write-Output '<-Start Result->'
Write-Output ('AOT Security Sweep | Computer=' + $env:COMPUTERNAME + ' | Collection=' + $overallStatus + ' | DurationSec=' + $seconds)
Write-Output ('Findings | High=' + $counts['High'] + ' Medium=' + $counts['Medium'] + ' Low=' + $counts['Low'] + ' Info=' + $counts['Info'] + ' Omitted=' + $report['summary']['omitted_findings'])
Write-Output ('Coverage | DefenderAV=' + $script:DefenderCoverage['antivirus_status'] + ' Preferences=' + $script:DefenderCoverage['preferences_status'] + ' DefenderDetections=' + $script:DefenderCoverage['detection_status'] + ' SignedSecurityInventory=' + $script:Stats['expected_signed_security_components'])
$preview = @($sorted | Where-Object { $_.severity -eq 'High' -or $_.severity -eq 'Medium' } | Select-Object -First 5)
foreach ($hit in $preview) {
    Write-Output (Short-Text ('REVIEW [' + $hit.severity + '] ' + $hit.category + ' - ' + $hit.title + ' - ' + $hit.name + ' - ' + $hit.path) 240)
}
if ($script:CollectionProblems.Count -gt 0) {
    Write-Output ('Incomplete sections: ' + ((@($script:CollectionProblems.ToArray() | Select-Object -ExpandProperty section -Unique | Select-Object -First 7)) -join ', '))
}
foreach ($optional in @($script:OptionalSections.ToArray() | Select-Object -First 2)) {
    Write-Output (Short-Text ('Optional coverage: ' + $optional.section + '=' + $optional.status + ' (' + $optional.reason + ')') 190)
}
Write-Output 'AOT_SECURITY_JSON_BEGIN'
Write-Output $json
Write-Output 'AOT_SECURITY_JSON_END'
$criticalMissing = @($script:CollectionProblems.ToArray() | Where-Object {
    $_.section -in @('Processes','Services','TCP','ScheduledTasks','RegistryAutoruns')
}).Count -gt 0
if ($MonitorMode -and ($counts['High'] -gt 0 -or $criticalMissing)) { exit 1 }
exit 0
