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
            mac_last6 = if ($a.MacAddress) { ([string]$a.MacAddress) -replace '^.*(?=.{6}$)', '' } else { '' }
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
