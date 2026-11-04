# AOT - Network and DNS Diagnostics [WIN]
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

# AOT Network and DNS Diagnostics - read-only first-pass endpoint/network/domain evidence.
$report = New-AotReport 'network-and-dns-diagnostics'
function Invoke-AotTcpProbe {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 1300)
    $tcp = New-Object Net.Sockets.TcpClient
    try {
        $async = $tcp.BeginConnect($HostName, $Port, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne($TimeoutMs)
        if (!$ok) { return @{ destination = $HostName; port = $Port; result = 'timeout' } }
        $tcp.EndConnect($async)
        return @{ destination = $HostName; port = $Port; result = 'connected' }
    } catch {
        return @{ destination = $HostName; port = $Port; result = 'failed'; error = Limit-AotText $_.Exception.Message 100 }
    } finally { $tcp.Close() }
}
function Invoke-AotResolve {
    param([string]$Name, [string]$Server = '')
    try {
        $options = @{ Name = $Name; Type = 'A'; QuickTimeout = $true; ErrorAction = 'Stop' }
        if ($Server) { $options.Server = $Server }
        $out = @(Resolve-DnsName @options | Where-Object { $_.IPAddress } | Select-Object -First 8 -ExpandProperty IPAddress)
        return @{ name = $Name; server = $Server; addresses = $out; success = ($out.Count -gt 0) }
    } catch {
        return @{ name = $Name; server = $Server; success = $false; error = Limit-AotText $_.Exception.Message 130 }
    }
}
Invoke-AotSection $report 'adapters_ip_dns' {
    $adapters = @(Get-NetAdapter -ErrorAction Stop | Select-Object -First 30)
    $results = @(foreach ($a in $adapters) {
        $ip = @(Get-NetIPAddress -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue | Where-Object {
            $_.AddressFamily -in @('IPv4','IPv6') -and $_.IPAddress -notmatch '^(fe80:|169\.254\.)'
        } | Select-Object -First 12 | ForEach-Object {
            @{ address = $_.IPAddress; prefix_length = $_.PrefixLength; family = [string]$_.AddressFamily; origin = [string]$_.PrefixOrigin }
        })
        $dns = @(Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue | ForEach-Object ServerAddresses | Select-Object -Unique)
        $gw = @(Get-NetRoute -InterfaceIndex $a.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 3 | ForEach-Object NextHop)
        [ordered]@{ name = $a.Name; description = Limit-AotText $a.InterfaceDescription 100
            state = [string]$a.Status; link_speed = [string]$a.LinkSpeed
            mac_last6 = if ($a.MacAddress) {
                $hexOnly = ([string]$a.MacAddress) -replace '[^a-fA-F0-9]', ''
                if ($hexOnly.Length -ge 6) { $hexOnly.Substring($hexOnly.Length - 6) } else { '' }
            } else { '' }
            ipv4_ipv6 = $ip; dns_servers = $dns; gateways = $gw; interface_index = $a.ifIndex }
    })
    $warnings = @()
    if ($adapters.Count -ge 30) { $warnings += 'Adapter inventory capped at 30' }
    if (@($results | Where-Object { $_.state -eq 'Up' -and @($_.dns_servers).Count -eq 0 }).Count -gt 0) {
        Add-AotFinding $report 'warning' 'ACTIVE_ADAPTER_NO_DNS' 'One or more active adapters have no configured DNS servers'
    }
    return @{ data = $results; warnings = $warnings }
}
Invoke-AotSection $report 'routes_and_profiles' {
    $warnings = @(); $data = [ordered]@{}
    try {
        $data.default_routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
            Sort-Object RouteMetric | Select-Object -First 12 InterfaceIndex,NextHop,RouteMetric,InterfaceMetric)
    } catch { $warnings += 'IPv4 default routes unavailable' }
    try {
        $data.profiles = @(Get-NetConnectionProfile -ErrorAction Stop | Select-Object -First 20 InterfaceAlias,NetworkCategory,IPv4Connectivity,IPv6Connectivity)
    } catch { $warnings += 'Network profiles unavailable' }
    try {
        $data.dhcp = @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True' -ErrorAction Stop |
            Select-Object -First 12 Description,DHCPEnabled,DHCPServer,DHCPLeaseObtained,DHCPLeaseExpires)
    } catch { $warnings += 'DHCP data unavailable' }
    return @{ data = $data; warnings = $warnings }
}
Invoke-AotSection $report 'dns_client_and_resolution' {
    $warnings = @(); $data = [ordered]@{}
    $adapterDns = @(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.ServerAddresses.Count -gt 0 } | Select-Object -First 16)
    $servers = @($adapterDns | ForEach-Object { $_.ServerAddresses } | Where-Object { $_ } | Select-Object -Unique -First 6)
    $data.dns_servers = $servers
    try {
        $data.suffixes = @(Get-DnsClientGlobalSetting -ErrorAction Stop | Select-Object SuffixSearchList,UseDevolution,DevolutionLevel)
    } catch { $warnings += 'DNS suffix search list unavailable' }
    try {
        $data.client_cache = @(Get-DnsClientCache -ErrorAction Stop | Group-Object Status |
            Select-Object -First 8 Name,Count)
    } catch { $warnings += 'DNS cache summary unavailable' }
    $testNames = @($env:COMPUTERNAME)
    $domainName = ''
    try {
        $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        if ($cs.PartOfDomain) { $domainName = [string]$cs.Domain; $testNames += $domainName }
    } catch { $warnings += 'Domain context unavailable' }
    if ([string]$env:DiagTargetHost -and $env:DiagTargetHost -match '^[A-Za-z0-9][A-Za-z0-9.-]{0,251}$') {
        $testNames += [string]$env:DiagTargetHost
    } elseif ([string]$env:DiagTargetHost) {
        $warnings += 'DiagTargetHost rejected: invalid hostname format'
    }
    $testNames = @($testNames | Select-Object -Unique -First 3)
    $tests = @()
    foreach ($name in $testNames) {
        $tests += Invoke-AotResolve -Name $name
        foreach ($server in @($servers | Select-Object -First 3)) {
            $tests += Invoke-AotResolve -Name $name -Server $server
        }
    }
    $data.resolution_tests = $tests
    if (@($tests | Where-Object { $_.success -eq $false }).Count -gt 0) {
        Add-AotFinding $report 'warning' 'DNS_QUERY_FAILURE' 'At least one observed DNS query failed; review server and name-specific evidence'
    }
    return @{ data = $data; warnings = $warnings }
}
Invoke-AotSection $report 'domain_and_time' {
    $warnings = @()
    $result = [ordered]@{}
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $result.joined = [bool]$cs.PartOfDomain
    $result.domain = [string]$cs.Domain
    $result.role = [int]$cs.DomainRole
    $result.time = Get-AotTimeStatus
    $result.dc = @{}
    if ($cs.PartOfDomain) {
        try {
            $nl = @(& "$env:SystemRoot\System32\nltest.exe" ('/dsgetdc:' + $cs.Domain) 2>&1)
            $result.dc.discovery_output_excerpt = Limit-AotText ($nl -join ' ') 650
            if ($LASTEXITCODE -ne 0) { $warnings += 'DC discovery returned ' + $LASTEXITCODE }
        } catch { $warnings += 'DC discovery failed: ' + (Limit-AotText $_.Exception.Message 130) }
        try {
            $secure = Test-ComputerSecureChannel -ErrorAction Stop
            $result.secure_channel = [bool]$secure
            if (!$secure) { Add-AotFinding $report 'warning' 'DOMAIN_TRUST' 'Machine secure channel check returned false; no repair attempted' }
        } catch { $warnings += 'Machine trust read unavailable (DC or unsupported role): ' + (Limit-AotText $_.Exception.Message 100) }
        try {
            $srv = @(Resolve-DnsName -Name ('_ldap._tcp.dc._msdcs.' + $cs.Domain) -Type SRV -QuickTimeout -ErrorAction Stop |
                Where-Object { $_.NameTarget } | Select-Object -First 8 NameTarget,Port,Priority,Weight)
            $result.dc.srv_records = $srv
        } catch { $warnings += 'LDAP SRV lookup unavailable: ' + (Limit-AotText $_.Exception.Message 110) }
    } else { $result.secure_channel = 'not_applicable' }
    return @{ data = $result; warnings = $warnings }
}
Invoke-AotSection $report 'bounded_connectivity' {
    $warnings = @(); $probes = @()
    $ipcfg = @(Get-NetIPConfiguration -ErrorAction Stop | Where-Object { $_.IPv4Address } | Select-Object -First 8)
    $gateways = @($ipcfg | ForEach-Object { $_.IPv4DefaultGateway.NextHop } | Where-Object { $_ } | Select-Object -Unique -First 3)
    $dns = @($ipcfg | ForEach-Object { $_.DNSServer.ServerAddresses } | Where-Object { $_ -match '^\d{1,3}(\.\d{1,3}){3}$' } | Select-Object -Unique -First 3)
    foreach ($g in $gateways) {
        try {
            $p = Test-Connection -ComputerName $g -Count 1 -ErrorAction Stop
            $probes += @{ target = $g; mode = 'icmp'; result = 'reply'; latency_ms = $p.ResponseTime }
        } catch { $probes += @{ target = $g; mode = 'icmp'; result = 'no_reply'; note = 'ICMP may be blocked' } }
    }
    foreach ($server in $dns) { $probes += Invoke-AotTcpProbe -HostName $server -Port 53 -TimeoutMs 1300 }
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    if ($cs.PartOfDomain) {
        $records = @()
        try {
            $records = @(Resolve-DnsName -Name ('_ldap._tcp.dc._msdcs.' + $cs.Domain) -Type SRV -QuickTimeout -ErrorAction Stop |
                Where-Object { $_.NameTarget } | Select-Object -First 2)
        } catch { $warnings += 'No LDAP SRV targets available for TCP probes' }
        foreach ($record in $records) {
            $probes += Invoke-AotTcpProbe -HostName ([string]$record.NameTarget).TrimEnd('.') -Port 389 -TimeoutMs 1300
        }
    }
    return @{ data = $probes; warnings = $warnings }
}
Invoke-AotSection $report 'proxy_and_dns_events' {
    $warnings = @(); $data = [ordered]@{}
    try {
        $data.winhttp_proxy = Limit-AotText ((& "$env:SystemRoot\System32\netsh.exe" 'winhttp' 'show' 'proxy' 2>&1) -join ' ') 350
    } catch { $warnings += 'WinHTTP proxy unavailable' }
    $events = Get-AotEvents -LogName 'System' -EventIds @(1014,1001,4004,4013,5719,5722,40960,40961) -Days 3 -Limit 24
    $data.system_events = $events.data
    $warnings += @($events.warnings)
    return @{ data = $data; warnings = $warnings }
}
Write-AotReport $report
