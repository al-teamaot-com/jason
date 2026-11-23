$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RecoveryPrimitives.ps1')
$script:Passed = 0
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-Throws([scriptblock]$Action, [string]$Expected) {
    $caught = $false
    try { & $Action | Out-Null } catch {
        if ($_.Exception.Message -notlike "*$Expected*") { throw }
        $caught = $true
    }
    Assert-True $caught "Expected failure: $Expected"
}
function Test-Case([string]$Name, [scriptblock]$Action) {
    & $Action
    $script:Passed++
    Write-Output "PASS: $Name"
}
# Platform dependencies mocked; real temporary files/hashes/copy are used.
function Get-AuthenticodeSignature {
    param($LiteralPath, $ErrorAction)
    [pscustomobject]@{Status=$script:Signature; SignerCertificate=[pscustomobject]@{Thumbprint=('A'*40)}}
}
function Get-DebMsiIdentity {
    param($Path)
    [pscustomobject]@{ProductCode=$script:Product; ProductVersion='1.15.21'}
}
function Get-Service {
    param($Name, $ErrorAction)
    $service = [pscustomobject]@{ Status=$script:ServiceStatus }
    $service | Add-Member ScriptMethod WaitForStatus {
        param($Status, $Timeout)
        if ($script:WaitFails) { throw 'MOCK_WAIT_TIMEOUT' }
    }
    $service
}
function Start-Service {
    param($Name, $ErrorAction)
    Assert-True ($Name -eq 'DattoBackupAgentService') 'Wrong service'
    $script:Starts++; $script:ServiceStatus='Running'
}
function Get-DebAgentSnapshot {
    Assert-True ($script:ServiceStatus -eq 'Running') 'Registration before service Running'
    $script:StatusCalls++
    [pscustomobject]@{AgentId=$script:Agent; TenantId='tenant-original'}
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('aot-deb-test-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
try {
    $file = Join-Path $root 'download.msi'; [IO.File]::WriteAllText($file,'synthetic-not-an-installer')
    $alias = Join-Path $root 'agent.msi'
    $script:Signature='Valid'; $script:Product='product-original'
    $argsSource = @{DownloadedMsi=$file; ExpectedFileName='agent.msi'; ExpectedSha256=(Get-FileHash $file -Algorithm SHA256).Hash; ExpectedSignerThumbprint=('A'*40); ExpectedProductCode='product-original'; ExpectedVersion='1.15.21'}
    Test-Case 'default only plans source alias' {
        $r=Resolve-DebMsiSource @argsSource
        Assert-True ($r.State -eq 'WouldCreate' -and -not (Test-Path $alias)) 'Unexpected write'
    }
    Test-Case 'wrong source hash cannot create alias' {
        $a=$argsSource.Clone();$a.ExpectedSha256='0'*64
        Assert-Throws {Resolve-DebMsiSource @a -Apply} 'HASH_CHANGED'
        Assert-True (-not (Test-Path $alias)) 'Unexpected alias'
    }
    Test-Case 'untrusted signature cannot create alias' {
        $script:Signature='NotTrusted'
        Assert-Throws {Resolve-DebMsiSource @argsSource -Apply} 'SIGNATURE_REJECTED'
        $script:Signature='Valid'
    }
    Test-Case 'changed installed identity blocks copy' {
        $script:Product='other-product'
        Assert-Throws {Resolve-DebMsiSource @argsSource -Apply} 'IDENTITY_MISMATCH'
        $script:Product='product-original'
    }
    Test-Case 'source path traversal blocks copy' {
        $a=$argsSource.Clone();$a.ExpectedFileName='../escape.msi'
        Assert-Throws {Resolve-DebMsiSource @a -Apply} 'BASENAME_INVALID'
    }
    Test-Case 'existing different alias is preserved' {
        [IO.File]::WriteAllText($alias,'other-package')
        Assert-Throws {Resolve-DebMsiSource @argsSource -Apply} 'SOURCE_DIFFERS'
        Assert-True (([IO.File]::ReadAllText($alias)) -eq 'other-package') 'Overwrote alias'
        [IO.File]::Delete($alias)
    }
    Test-Case 'approved alias copies equal bytes once' {
        $r=Resolve-DebMsiSource @argsSource -Apply
        Assert-True ($r.State -eq 'Created' -and $r.Changed) 'Copy failed'
        $again=Resolve-DebMsiSource @argsSource -Apply
        Assert-True ($again.State -eq 'AlreadyMatched' -and -not $again.Changed) 'Not idempotent'
    }
    $script:ServiceStatus='Stopped';$script:Starts=0;$script:StatusCalls=0;$script:WaitFails=$false;$script:Agent='agent-original'
    $argsService=@{InstallerExitCode=0;ExpectedAgentId='agent-original';ExpectedTenantId='tenant-original'}
    Test-Case 'stopped service default is plan only' {
        $r=Confirm-DebPostInstall @argsService
        Assert-True ($r.State -eq 'WouldStartService' -and $script:Starts -eq 0) 'Unexpected start'
    }
    Test-Case 'MSI failure never starts service' {
        $a=$argsService.Clone();$a.InstallerExitCode=1603
        Assert-Throws {Confirm-DebPostInstall @a -Apply} 'INSTALLER_FAILED'
        Assert-True ($script:Starts -eq 0) 'Started after failure'
    }
    Test-Case '3010 requires review with no reboot or start' {
        $a=$argsService.Clone();$a.InstallerExitCode=3010
        $r=Confirm-DebPostInstall @a -Apply
        Assert-True ($r.State -eq 'RebootRequiredHumanReview' -and $script:Starts -eq 0) 'Unexpected action'
    }
    Test-Case 'start precedes status and preserves original identity' {
        $r=Confirm-DebPostInstall @argsService -Apply
        Assert-True ($r.Verified -and $script:Starts -eq 1 -and $script:StatusCalls -eq 1) 'Order failure'
    }
    Test-Case 'running service is never restarted' {
        $r=Confirm-DebPostInstall @argsService -Apply
        Assert-True ($r.Verified -and -not $r.Changed -and $script:Starts -eq 1) 'Unexpected restart'
    }
    Test-Case 'changed registration cannot pass postcheck' {
        $script:Agent='replacement'
        Assert-Throws {Confirm-DebPostInstall @argsService -Apply} 'REGISTRATION_CHANGED'
        $script:Agent='agent-original'
    }
    Test-Case 'pending service transition requires review' {
        $script:ServiceStatus='StopPending'
        Assert-Throws {Confirm-DebPostInstall @argsService -Apply} 'TRANSITION_REQUIRES_REVIEW'
        Assert-True ($script:Starts -eq 1) 'Unexpected start'
    }
    Test-Case 'service startup timeout cannot pass postcheck' {
        $script:ServiceStatus='Stopped';$script:WaitFails=$true
        Assert-Throws {Confirm-DebPostInstall @argsService -Apply} 'WAIT_TIMEOUT'
    }
    Write-Output "PASSED=$script:Passed; Windows COM/Authenticode/SCM/CLI integration is NOT proved by mocks."
} finally { if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force } }
