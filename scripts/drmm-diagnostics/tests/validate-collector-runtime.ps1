# Ephemeral Windows runner, PowerShell 5.1. Never run on a production endpoint.
# Validates standalone artifacts without Datto credentials or state mutation.
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$sourceDirectory = Join-Path $root 'components'
$exe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$names = @('windows-snapshot', 'disk-space-analysis', 'network-dns')
foreach ($name in $names) {
    $source = Join-Path $sourceDirectory ($name + '.ps1')
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw ('Missing expected generated script: ' + $name)
    }
    $tmp = Join-Path $env:RUNNER_TEMP ('drmm-diagnostic-' + $name)
    $stdout = $tmp + '.stdout.txt'
    $stderr = $tmp + '.stderr.txt'
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $arguments = @('-NoProfile', '-NonInteractive', '-File', ('"' + $source + '"'))
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $stopwatch.Stop()
    if ($process.ExitCode -ne 0) {
        $stderrText = ''
        if (Test-Path -LiteralPath $stderr) {
            $stderrText = (Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue)
        }
        throw ('Script ' + $name + ' returned ' + $process.ExitCode + '. Error type: ' + ($stderrText | Select-Object -First 1))
    }
    $text = Get-Content -LiteralPath $stdout -Raw
    if ($text.Length -gt 65536) {
        throw ('Unusable Datto output: ' + $name + ' length=' + $text.Length)
    }
    $begin = $text.IndexOf('AOT_DIAGNOSTIC_JSON_BEGIN', [StringComparison]::Ordinal)
    $end = $text.IndexOf('AOT_DIAGNOSTIC_JSON_END', [StringComparison]::Ordinal)
    if ($begin -lt 0 -or $end -le $begin) {
        throw ('Diagnostic output markers missing: ' + $name)
    }
    $start = $begin + 'AOT_DIAGNOSTIC_JSON_BEGIN'.Length
    $json = $text.Substring($start, $end - $start).Trim()
    $report = $json | ConvertFrom-Json
    if ($report.schema_version -ne '1.0' -or $report.read_only -ne $true) {
        throw ('Diagnostic schema / read-only contract failed: ' + $name)
    }
    if ($report.overall_status -eq 'unavailable' -or @($report.sections).Count -lt 5) {
        throw ('Insufficient diagnostic evidence: ' + $name)
    }
    Write-Output ('EPHEMERAL_WINDOWS_51_RUNTIME=PASS;COMPONENT=' + $name +
        ';SCRIPT_SEC=' + [Math]::Round($stopwatch.Elapsed.TotalSeconds, 1) +
        ';TEXT_CHARS=' + $text.Length +
        ';SECTIONS=' + @($report.sections).Count +
        ';COLLECTION=' + $report.overall_status)
}
Write-Output 'EPHEMERAL_WINDOWS_51_ALL_THREE=PASS'
