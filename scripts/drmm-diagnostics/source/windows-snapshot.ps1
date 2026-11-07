# AOT Windows Diagnostic Snapshot - wide, bounded first-pass observations.
$report = New-AotReport 'windows-diagnostic-snapshot'
Invoke-AotSection $report 'system' {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $bios = Get-CimInstance Win32_BIOS -ErrorAction Stop
    $cpu = @(Get-CimInstance Win32_Processor -ErrorAction Stop)
    $up = ((Get-Date) - $os.LastBootUpTime).TotalHours
    if ($up -lt 24) { Add-AotFinding $report 'info' 'RECENT_BOOT' ('Last boot ' + [Math]::Round($up, 1) + ' hours ago') }
    return @{ data = [ordered]@{
        os_caption = $os.Caption; os_version = $os.Version; build = $os.BuildNumber
        architecture = $os.OSArchitecture; last_boot = $os.LastBootUpTime.ToUniversalTime().ToString('o')
        uptime_hours = [Math]::Round($up, 1)
        manufacturer = $cs.Manufacturer; model = $cs.Model; domain = $cs.Domain
        domain_joined = [bool]$cs.PartOfDomain; role = $cs.DomainRole
        total_ram_gb = [Math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
        available_ram_gb = [Math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 2)
        cpu_names = @($cpu | Select-Object -ExpandProperty Name -Unique)
        cpu_load_pct = @($cpu | Select-Object -ExpandProperty LoadPercentage)
        bios_version = (Limit-AotText $bios.SMBIOSBIOSVersion 90)
        serial_last4 = if ([string]$bios.SerialNumber -and ([string]$bios.SerialNumber).Length -gt 4) { ([string]$bios.SerialNumber).Substring(([string]$bios.SerialNumber).Length - 4) } else { 'not_available' }
    } }
}
Invoke-AotSection $report 'fixed_disks' {
    $disks = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' -ErrorAction Stop | ForEach-Object {
        $free = [double]$_.FreeSpace; $size = [double]$_.Size
        $pct = if ($size -gt 0) { [Math]::Round($free * 100 / $size, 1) } else { $null }
        if ($null -ne $pct -and $pct -lt 10) { Add-AotFinding $report 'warning' 'DISK_LOW_FREE' ($_.DeviceID + ' free=' + $pct + '%') }
        [ordered]@{ drive = $_.DeviceID; size_gb = [Math]::Round($size / 1GB, 2)
            free_gb = [Math]::Round($free / 1GB, 2); free_percent = $pct; file_system = $_.FileSystem }
    })
    return @{ data = $disks }
}
Invoke-AotSection $report 'pending_reboot_and_updates' {
    $reboot = Get-AotPendingReboot
    if (@($reboot.Values | Where-Object { $_ -eq $true }).Count -gt 0) {
        Add-AotFinding $report 'info' 'PENDING_REBOOT' 'Windows reboot indicators present; no restart attempted'
    }
    $warn = @()
    $patches = @()
    try { $patches = @(Get-HotFix -ErrorAction Stop | Sort-Object InstalledOn -Descending | Select-Object -First 12 HotFixID,InstalledOn,Description) }
    catch { $warn += 'Hotfix history unavailable: ' + (Limit-AotText $_.Exception.Message 130) }
    return @{ data = @{ pending_reboot = $reboot; recent_hotfixes = $patches }; warnings = $warn }
}
Invoke-AotSection $report 'service_health' {
    $expected = @('EventLog','Schedule','Winmgmt','wuauserv','BITS','Dnscache','LanmanWorkstation','Netlogon','W32Time','MpsSvc','WinDefend','VSS')
    $results = @(foreach ($name in $expected) {
        $s = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($null -eq $s) { [ordered]@{ name = $name; state = 'not_installed'; start_mode = $null }; continue }
        $wmi = Get-CimInstance Win32_Service -Filter ("Name='" + $name + "'") -ErrorAction SilentlyContinue
        [ordered]@{ name = $name; state = [string]$s.Status; start_mode = if ($wmi) {$wmi.StartMode} else {$null} }
    })
    foreach ($svc in $results) {
        if ($svc.start_mode -eq 'Auto' -and $svc.state -eq 'Stopped') {
            Add-AotFinding $report 'warning' 'AUTO_SERVICE_STOPPED' ($svc.name + ' is stopped despite automatic start')
        }
    }
    return @{ data = $results }
}
Invoke-AotSection $report 'security_configuration' {
    $warnings = @()
    $data = [ordered]@{}
    try {
        $data.firewall = @(Get-NetFirewallProfile -ErrorAction Stop | Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction)
    } catch { $warnings += 'Firewall profiles: ' + (Limit-AotText $_.Exception.Message 120) }
    try {
        $vols = @(Get-BitLockerVolume -ErrorAction Stop | Select-Object MountPoint,VolumeStatus,ProtectionStatus,EncryptionPercentage)
        $data.bitlocker = $vols
    } catch { $warnings += 'BitLocker status unavailable: ' + (Limit-AotText $_.Exception.Message 120) }
    try {
        $tp = Get-Tpm -ErrorAction Stop
        $data.tpm = @{ present = [bool]$tp.TpmPresent; ready = [bool]$tp.TpmReady; enabled = [bool]$tp.TpmEnabled }
    } catch { $warnings += 'TPM unavailable: ' + (Limit-AotText $_.Exception.Message 120) }
    try {
        if (Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue) {
            $mp = Get-MpComputerStatus -ErrorAction Stop
            $data.microsoft_defender = @{ antivirus_enabled = $mp.AntivirusEnabled; real_time_enabled = $mp.RealTimeProtectionEnabled
                signatures_age_days = $mp.AntivirusSignatureAge; service_enabled = $mp.AMServiceEnabled }
        } else { $warnings += 'Defender cmdlets unavailable' }
    } catch { $warnings += 'Defender status: ' + (Limit-AotText $_.Exception.Message 120) }
    return @{ data = $data; warnings = $warnings }
}
Invoke-AotSection $report 'network_summary' {
    $warn = @()
    $data = [ordered]@{}
    try {
        $data.adapters = @(Get-NetIPConfiguration -ErrorAction Stop | Select-Object -First 12 | ForEach-Object {
            [ordered]@{ interface = $_.InterfaceAlias; ipv4 = @($_.IPv4Address | ForEach-Object IPAddress)
                gateway = @($_.IPv4DefaultGateway | ForEach-Object NextHop)
                dns = @($_.DNSServer.ServerAddresses) }
        })
    } catch { $warn += 'IP configuration unavailable: ' + (Limit-AotText $_.Exception.Message 120) }
    try {
        $data.profiles = @(Get-NetConnectionProfile -ErrorAction Stop | Select-Object InterfaceAlias,NetworkCategory,IPv4Connectivity)
    } catch { $warn += 'Network profiles unavailable: ' + (Limit-AotText $_.Exception.Message 120) }
    return @{ data = $data; warnings = $warn }
}
Invoke-AotSection $report 'time_and_domain' {
    $warnings = @()
    $domain = @{}
    try {
        $domain.computer = @(Get-CimInstance Win32_ComputerSystem -ErrorAction Stop | Select-Object Domain,PartOfDomain,DomainRole)
    } catch { $warnings += 'Domain membership unavailable' }
    try {
        if (@($domain.computer)[0].PartOfDomain) {
            $dc = & "$env:SystemRoot\System32\nltest.exe" '/dsgetdc:' + ([string]@($domain.computer)[0].Domain) 2>&1
            $domain.dc_discovery_excerpt = Limit-AotText ($dc -join ' ') 450
        }
    } catch { $warnings += 'DC discovery unavailable: ' + (Limit-AotText $_.Exception.Message 110) }
    $domain.time = Get-AotTimeStatus
    return @{ data = $domain; warnings = $warnings }
}
Invoke-AotSection $report 'recent_event_evidence' {
    $s = Get-AotEvents -LogName 'System' -EventIds @(41,55,57,129,153,157,6008,7000,7001,7031,7034,7040) -Days 3 -Limit 28
    $a = Get-AotEvents -LogName 'Application' -EventIds @(1000,1001,1002,1026) -Days 3 -Limit 16
    if (@($s.data).Count -gt 0) { Add-AotFinding $report 'info' 'SYSTEM_EVENTS' ([string]@($s.data).Count + ' relevant system events in sampled window') }
    return @{ data = @{ system = $s.data; application = $a.data }; warnings = @($s.warnings) + @($a.warnings) }
}
Invoke-AotSection $report 'failed_scheduled_tasks' {
    $warnings = @(); $failed = @(); $inspected = 0
    try {
        if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
            $tasks = @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskPath -notlike '\Microsoft\*' } | Select-Object -First 100)
            $inspected = $tasks.Count
            $failed = @(foreach ($task in $tasks) {
                try {
                    $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath -ErrorAction Stop
                    if ($info.LastTaskResult -notin @(0,267009,267010,267011)) {
                        [ordered]@{ task = (Limit-AotText ($task.TaskPath + $task.TaskName) 150); last_result = $info.LastTaskResult; last_run = $info.LastRunTime }
                    }
                } catch { $warnings += 'At least one task status unavailable' }
            })
            $failed = @($failed | Select-Object -First 20)
            if ($tasks.Count -ge 100) { $warnings += 'Task inspection capped at 100 non-Microsoft tasks' }
        } else { $warnings += 'ScheduledTasks module unavailable' }
    } catch { $warnings += 'Task inventory failed: ' + (Limit-AotText $_.Exception.Message 120) }
    return @{ data = @{ inspected = $inspected; nonzero_results = $failed }; warnings = @($warnings | Select-Object -Unique) }
}
Write-AotReport $report
