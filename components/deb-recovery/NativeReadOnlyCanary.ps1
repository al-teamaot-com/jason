#requires -Version 5.1
# Candidate only: never published or executed by importing this repository.
$ErrorActionPreference = 'Stop'
try {
    if (-not $env:AOTDebCanaryProfile) { throw 'DEB_CANARY_PROFILE_REQUIRED' }
    $profile = $env:AOTDebCanaryProfile | ConvertFrom-Json -ErrorAction Stop
    $allowed = @('hostname','downloaded_msi','expected_filename','sha256','product_code','version','agent_id','tenant_id')
    foreach ($property in $profile.PSObject.Properties) {
        if ($allowed -notcontains $property.Name) { throw 'DEB_CANARY_UNKNOWN_INPUT' }
    }
    foreach ($name in $allowed) {
        if (-not ($profile.$name -is [string]) -or -not $profile.$name.Trim()) { throw 'DEB_CANARY_INPUT_MISSING' }
    }
    if ($env:COMPUTERNAME -ne $profile.hostname) { throw 'DEB_CANARY_WRONG_ENDPOINT' }
    $helper = Join-Path $PSScriptRoot 'RecoveryPrimitives.ps1'
    # The approved RMM component manifest must bind this attached file hash;
    # no runtime path or code is accepted from the input profile.
    if ((Get-FileHash -LiteralPath $helper -Algorithm SHA256 -ErrorAction Stop).Hash -ne 'a03857b45cd92391272daf5af341535ec9778c0ef19ebb200e2a502080e93a46') { throw 'DEB_CANARY_HELPER_HASH_CHANGED' }
    . $helper
    # The canary pins exact MSI bytes already reviewed in the incident. It may
    # inspect that package's public signer for this read-only check; this is
    # not a standing signer policy for a modifying component.
    if ((Get-FileHash -LiteralPath $profile.downloaded_msi -Algorithm SHA256 -ErrorAction Stop).Hash -ne $profile.sha256) { throw 'DEB_CANARY_MSI_HASH_CHANGED' }
    $publicSignature = Get-AuthenticodeSignature -LiteralPath $profile.downloaded_msi -ErrorAction Stop
    if ($publicSignature.Status -ne 'Valid' -or $null -eq $publicSignature.SignerCertificate) { throw 'DEB_CANARY_SIGNATURE_INVALID' }
    $sourceArguments = @{
        DownloadedMsi=$profile.downloaded_msi; ExpectedFileName=$profile.expected_filename
        ExpectedSha256=$profile.sha256; ExpectedSignerThumbprint=$publicSignature.SignerCertificate.Thumbprint
        ExpectedProductCode=$profile.product_code; ExpectedVersion=$profile.version
    }
    # No -Apply, installer launch, backup request, restart, cleanup or policy write.
    $source = Resolve-DebMsiSource @sourceArguments
    $agent = Confirm-DebPostInstall -InstallerExitCode 0 -ExpectedAgentId $profile.agent_id -ExpectedTenantId $profile.tenant_id
    [pscustomobject]@{
        mode='native_readonly_canary'; source_state=$source.State
        service_state=$agent.State; original_registration_verified=$agent.Verified
        changed=$false; installer_executed=$false; backup_started=$false
        production_acceptance_complete=$false
    } | ConvertTo-Json -Compress
    exit 0
} catch {
    # Do not echo provider values, paths, input profiles, command lines or errors.
    Write-Output 'DEB_NATIVE_READONLY_CANARY_FAILED_CLOSED'
    exit 1
}
