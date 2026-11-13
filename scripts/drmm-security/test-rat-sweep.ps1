#requires -Version 5.1
# Pure, isolated test harness: never executes the endpoint inventory script.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SourcePath
)
$ErrorActionPreference = 'Stop'
$src = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $SourcePath).Path)
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path -LiteralPath $SourcePath).Path, [ref]$tokens, [ref]$parseErrors)
if (@($parseErrors).Count -ne 0) { throw "PowerShell 5.1 parse errors: $(@($parseErrors).Count)" }

# Safe collection is source-controlled: inspect command ASTs, don't execute.
$mutating = New-Object 'System.Collections.Generic.List[string]'
foreach ($node in @($ast.FindAll({
    param($n) $n -is [System.Management.Automation.Language.CommandAst]
}, $true))) {
    $name = [string]$node.GetCommandName()
    if ($name -match '(?i)^(Remove|Set|New|Restart|Stop|Start|Disable|Enable|Uninstall|Install|Clear|Invoke-WebRequest|Invoke-RestMethod|Invoke-Expression)-' -and
        $name -notin @('New-Object')) {
        $mutating.Add($name)
    }
}
if ($mutating.Count) { throw ('Unsafe invocation found: ' + ($mutating -join ', ')) }
$needed = @('Get-PathClass','Get-ExpectedSignedSecurityComponent','Add-Problem','Add-OptionalSection')
$funcs = @($ast.FindAll({
    param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]
}, $true))
foreach ($name in $needed) {
    $def = @($funcs | Where-Object Name -eq $name)
    if ($def.Count -ne 1) { throw ('Required classifier missing or duplicated: ' + $name) }
    . ([scriptblock]::Create($def[0].Extent.Text))
}
$script:MockSignature='Valid'
$script:MockSigner='CN=Microsoft Windows Publisher, O=Microsoft Corporation'
$script:MockHidden=$false
$script:MockExists=$true
function Get-FileFacts {
    param([string]$Path)
    [pscustomobject]@{
        signature=$script:MockSignature
        signer_subject=$script:MockSigner
        hidden=$script:MockHidden
        exists=$script:MockExists
    }
}
function Assert-Equal {
    param([object]$Actual,[object]$Expected,[string]$Description)
    if ([string]$Actual -cne [string]$Expected) {
        throw ('FAIL: '+$Description+' actual='+[string]$Actual+' expected='+[string]$Expected)
    }
    $script:Assertions++
}
$script:Assertions=0
$defenderPath='C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.26000.1-0\MsMpEng.exe'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name WinDefend -Path $defenderPath) 'ExpectedSignedMicrosoftDefenderService' 'Exact signed Defender service'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name NotWinDefend -Path $defenderPath) '' 'Wrong service name'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name WinDefend -Path 'C:\Users\Public\MsMpEng.exe') '' 'Unexpected high-risk path'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name WinDefend -Path $defenderPath -Signals @('EncodedPowerShell')) '' 'Independent command signal persists'
$script:MockSignature='NotSigned'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name WinDefend -Path $defenderPath) '' 'Unsigned masquerade never trusted'
$script:MockSignature='Valid';$script:MockSigner='CN=Unrelated Software Company'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name WinDefend -Path $defenderPath) '' 'Unrecognized publisher never trusted'
$script:MockSigner='CN=Datto, LLC, O=Datto, LLC'
$dattoPath='C:\ProgramData\CentraStage\AEMAgent\RMM.AdvancedThreatDetection\dattoav\Endpoint Protection SDK\endpointprotection.exe'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name EndpointProtectionService -Path $dattoPath) 'ExpectedSignedAOTSecurityComponent' 'Expected signed Datto AV'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind RegistryAutorun -Name 'Datto EDR' -Path $dattoPath) 'ExpectedSignedAOTSecurityComponent' 'Expected signed AOT EDR'
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name EndpointProtectionService -Path 'C:\Users\Public\Endpoint Protection SDK\endpointprotection.exe') '' 'Unexpected Datto path'
$script:MockHidden=$true
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name EndpointProtectionService -Path $dattoPath) '' 'Hidden signed file is not automatically trusted'
$script:MockHidden=$false;$script:MockExists=$false
Assert-Equal (Get-ExpectedSignedSecurityComponent -Kind Service -Name EndpointProtectionService -Path $dattoPath) '' 'Missing file is not trusted'

# Exercise exactly the Defender telemetry statements with synthetic cmdlets and
# no disk, registry, network, process, service or provider changes.
$begin = $src.IndexOf('# Defender telemetry is optional when Datto AV')
$end = $src.IndexOf('# Higher-priority findings appear first', $begin)
if ($begin -lt 0 -or $end -lt 0) { throw 'Defender telemetry section unavailable' }
$defenderSection = [scriptblock]::Create($src.Substring($begin, $end-$begin))
$script:MockRunningMode='Not running'
$script:MockAVEnabled=$false
$script:PrefCallCount=0
$script:PrefShouldThrow=$true
function Get-MpComputerStatus {
    [pscustomobject]@{AMRunningMode=$script:MockRunningMode;AntivirusEnabled=$script:MockAVEnabled}
}
function Get-MpThreatDetection { @() }
function Get-MpPreference {
    $script:PrefCallCount++
    if ($script:PrefShouldThrow) { throw 'Access denied, synthetic independent preference failure' }
    [pscustomobject]@{ExclusionPath=@()}
}
function Add-Finding { param([string]$Severity,[string]$Category,[string]$Title,[string]$Name,[string]$Path) }
function Reset-SyntheticTelemetry {
    $script:OptionalSections=New-Object 'System.Collections.Generic.List[object]'
    $script:CollectionProblems=New-Object 'System.Collections.Generic.List[object]'
    $script:DefenderCoverage=[ordered]@{antivirus_status='unknown';preferences_status='not_checked';detection_status='not_checked';preferences_reason=''}
    $script:Stats=[ordered]@{defender_detections=0}
    $script:PrefCallCount=0
}
Reset-SyntheticTelemetry
. $defenderSection
Assert-Equal $script:DefenderCoverage.preferences_status 'skipped_inactive' 'Inactive Defender skips preference query'
Assert-Equal $script:PrefCallCount 0 'No inactive Defender preference query executed'
Assert-Equal $script:CollectionProblems.Count 0 'Inactive Defender not a collection failure'
Assert-Equal $script:OptionalSections.Count 1 'Inactive Defender recorded as optional coverage'
$script:MockRunningMode='Normal';$script:MockAVEnabled=$true
Reset-SyntheticTelemetry
. $defenderSection
Assert-Equal $script:DefenderCoverage.preferences_status 'error' 'Unexpected active Defender failure recorded'
Assert-Equal $script:CollectionProblems.Count 1 'Active Defender collection failure not hidden'
$script:PrefShouldThrow=$false
Reset-SyntheticTelemetry
. $defenderSection
Assert-Equal $script:DefenderCoverage.preferences_status 'collected' 'Healthy active Defender preference collection'
Assert-Equal $script:CollectionProblems.Count 0 'Healthy Defender does not cause a collection error'
Write-Output ('AOT_RAT_SWEEP_TESTS=PASS ASSERTIONS='+$script:Assertions)
