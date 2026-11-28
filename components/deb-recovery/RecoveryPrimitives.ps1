#requires -Version 5.1
# Original AOT helper functions, not a redistribution of the ComStore script.
# No top-level action. Dot-source only inside an exact reviewed RMM component.
# -Apply is an execution switch, not authorization. The existing orchestrator
# must establish exact action authority, client scope and maintenance gates.

function Get-DebMsiIdentity {
    param([Parameter(Mandatory=$true)][string]$Path)
    $installer = $null; $database = $null
    try {
        $installer = New-Object -ComObject WindowsInstaller.Installer
        $database = $installer.OpenDatabase($Path, 0)
        $values = @{}
        foreach ($name in @('ProductCode','ProductVersion')) {
            $view = $null; $record = $null
            try {
                $view = $database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property``='$name'")
                $view.Execute(); $record = $view.Fetch()
                if ($null -eq $record) { throw 'DEB_MSI_IDENTITY_MISSING' }
                $values[$name] = $record.StringData(1)
            } finally {
                if ($null -ne $view) { $view.Close(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($view) }
                if ($null -ne $record) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($record) }
            }
        }
        [pscustomobject]$values
    } finally {
        if ($null -ne $database) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($database) }
        if ($null -ne $installer) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($installer) }
    }
}

function Resolve-DebMsiSource {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$DownloadedMsi,
        [Parameter(Mandatory=$true)][string]$ExpectedFileName,
        [Parameter(Mandatory=$true)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ExpectedSha256,
        [Parameter(Mandatory=$true)][ValidatePattern('^[A-Fa-f0-9]{40}$')][string]$ExpectedSignerThumbprint,
        [Parameter(Mandatory=$true)][string]$ExpectedProductCode,
        [Parameter(Mandatory=$true)][string]$ExpectedVersion,
        [switch]$Apply
    )
    # Expected filename/product/version come from installed MSI registration;
    # package hash and signer come from the exact reviewed downloaded package.
    if ($ExpectedFileName -notmatch '^[A-Za-z0-9_. -]+\.msi$' -or
        $ExpectedFileName -eq '.msi') { throw 'DEB_SOURCE_BASENAME_INVALID' }
    $source = Get-Item -LiteralPath $DownloadedMsi -Force -ErrorAction Stop
    if ($source.PSIsContainer -or $source.Extension -ne '.msi') { throw 'DEB_MSI_PATH_INVALID' }
    $node = $source
    while ($null -ne $node) {
        if ($node.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'DEB_REPARSE_PATH_REJECTED' }
        if ($node -is [IO.FileInfo]) { $node = $node.Directory } else { $node = $node.Parent }
    }
    $hash = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
    if ($hash -ne $ExpectedSha256) { throw 'DEB_DOWNLOADED_HASH_CHANGED' }
    $signature = Get-AuthenticodeSignature -LiteralPath $source.FullName -ErrorAction Stop
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
        $signature.SignerCertificate.Thumbprint -ne $ExpectedSignerThumbprint) { throw 'DEB_SIGNATURE_REJECTED' }
    $identity = Get-DebMsiIdentity -Path $source.FullName
    if ($identity.ProductCode -ne $ExpectedProductCode -or $identity.ProductVersion -ne $ExpectedVersion) {
        throw 'DEB_INSTALLED_MSI_IDENTITY_MISMATCH'
    }
    $destination = Join-Path $source.DirectoryName $ExpectedFileName
    if (Test-Path -LiteralPath $destination) {
        $existing = Get-Item -LiteralPath $destination -Force -ErrorAction Stop
        if ($existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'DEB_EXISTING_SOURCE_PATH_REJECTED'
        }
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256 -ErrorAction Stop).Hash -ne $hash) {
            throw 'DEB_EXISTING_SOURCE_DIFFERS'
        }
        return [pscustomobject]@{ State='AlreadyMatched'; Changed=$false; SourcePath=$destination; Sha256=$hash }
    }
    if (-not $Apply) {
        return [pscustomobject]@{ State='WouldCreate'; Changed=$false; SourcePath=$destination; Sha256=$hash }
    }
    # Copy without overwrite: competing writers fail rather than replace data.
    [IO.File]::Copy($source.FullName, $destination, $false)
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256 -ErrorAction Stop).Hash -ne $hash) {
        throw 'DEB_ALIAS_POSTCOPY_HASH_MISMATCH'
    }
    [pscustomobject]@{ State='Created'; Changed=$true; SourcePath=$destination; Sha256=$hash }
}

function Get-DebAgentSnapshot {
    $path = Join-Path $env:ProgramFiles 'Datto Backup Agent\DattoBackupAgentStatus.exe'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'DEB_NATIVE_STATUS_MISSING' }
    $process = New-Object Diagnostics.Process
    try {
        $process.StartInfo.FileName = $path
        $process.StartInfo.Arguments = 'get-status'
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(30000)) {
            $process.Kill(); throw 'DEB_NATIVE_STATUS_TIMEOUT'
        }
        $text = $stdout.GetAwaiter().GetResult()
        [void]$stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw 'DEB_NATIVE_STATUS_FAILED' }
        $agent = [regex]::Match($text, '(?im)^\s*Agent ID:\s*(\S+)\s*$')
        $tenant = [regex]::Match($text, '(?im)^\s*Tenant ID:\s*(\S+)\s*$')
        if (-not $agent.Success -or -not $tenant.Success) { throw 'DEB_NATIVE_IDENTITY_UNPARSEABLE' }
        [pscustomobject]@{ AgentId=$agent.Groups[1].Value; TenantId=$tenant.Groups[1].Value }
    } finally { $process.Dispose() }
}

function Confirm-DebPostInstall {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][int]$InstallerExitCode,
        [Parameter(Mandatory=$true)][string]$ExpectedAgentId,
        [Parameter(Mandatory=$true)][string]$ExpectedTenantId,
        [switch]$Apply
    )
    if (-not $ExpectedAgentId.Trim() -or -not $ExpectedTenantId.Trim()) { throw 'DEB_ORIGINAL_IDENTITY_REQUIRED' }
    if ($InstallerExitCode -eq 3010) {
        return [pscustomobject]@{ State='RebootRequiredHumanReview'; Changed=$false; Verified=$false }
    }
    if ($InstallerExitCode -ne 0) { throw 'DEB_INSTALLER_FAILED_NO_SERVICE_ACTION' }
    $service = Get-Service -Name DattoBackupAgentService -ErrorAction Stop
    $changed = $false
    if ($service.Status -ne 'Running') {
        if ($service.Status -ne 'Stopped') { throw 'DEB_SERVICE_TRANSITION_REQUIRES_REVIEW' }
        if (-not $Apply) {
            return [pscustomobject]@{ State='WouldStartService'; Changed=$false; Verified=$false }
        }
        Start-Service -Name DattoBackupAgentService -ErrorAction Stop
        $changed = $true
        $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    }
    if ((Get-Service -Name DattoBackupAgentService -ErrorAction Stop).Status -ne 'Running') {
        throw 'DEB_SERVICE_NOT_RUNNING'
    }
    $snapshot = Get-DebAgentSnapshot
    if ($snapshot.AgentId -ne $ExpectedAgentId -or $snapshot.TenantId -ne $ExpectedTenantId) {
        throw 'DEB_ORIGINAL_REGISTRATION_CHANGED'
    }
    [pscustomobject]@{ State='RunningOriginalPairing'; Changed=$changed; Verified=$true }
}
