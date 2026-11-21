# Run with Windows PowerShell 5.1: powershell.exe -NoProfile -NonInteractive -File .\report-contract.ps1
# Synthetic only: does not invoke endpoint collectors or read client data.
$ErrorActionPreference = 'Stop'
$common = Join-Path (Split-Path $PSScriptRoot -Parent) 'source\common.ps1'
. $common
$report = New-AotReport 'synthetic-contract-test'
Invoke-AotSection $report 'fixture_complete' { return @{data=@{value=42}} }
Invoke-AotSection $report 'fixture_partial' { return @{data=@{sampled=3};warnings=@('bounded scan');incomplete=$true} }
Invoke-AotSection $report 'fixture_unavailable' { throw 'synthetic failure' }
$actual = @($report.sections | ForEach-Object {$_.status})
$expected = @('complete','partial','unavailable')
if (($actual -join ',') -ne ($expected -join ',')) {
    throw ('Status mismatch: ' + ($actual -join ','))
}
$json = ConvertTo-Json -InputObject $report -Depth 15 -Compress
$object = $json | ConvertFrom-Json
if ($object.schema_version -ne '1.0' -or @($object.sections).Count -ne 3 -or $object.component -ne 'synthetic-contract-test') {
    throw 'Invalid schema, section count, or component in runtime JSON'
}
if ($json -match 'password|credential|secret' -or $json.Length -gt 8192) {
    throw 'Unexpected synthetic payload'
}
Write-Output ('SYNTHETIC_RUNTIME_TEST=PASS;PWSH_VERSION=' + $PSVersionTable.PSVersion.ToString() + ';SECTIONS=' + @($object.sections).Count + ';JSON_BYTES=' + $json.Length)
