param(
    [Parameter(Mandatory=$true)][string]$AppId,
    [Parameter(Mandatory=$true)][string]$ServicePrincipalObjectId,
    [Parameter(Mandatory=$true)][string]$Mailbox,
    [string]$DisplayName = "Jason Mail Read",
    [string]$ScopeName = "Jason Mail Read Pilot"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Module -ListAvailable ExchangeOnlineManagement)) {
    throw "ExchangeOnlineManagement module is required."
}

Import-Module ExchangeOnlineManagement
Connect-ExchangeOnline -ShowBanner:$false

try {
    $existingSp = Get-ServicePrincipal -Identity $ServicePrincipalObjectId -ErrorAction SilentlyContinue
    if (-not $existingSp) {
        New-ServicePrincipal -AppId $AppId -ObjectId $ServicePrincipalObjectId -DisplayName $DisplayName | Out-Null
    }

    $scopeFilter = "EmailAddresses -eq 'SMTP:$Mailbox'"
    $existingScope = Get-ManagementScope -Identity $ScopeName -ErrorAction SilentlyContinue
    if (-not $existingScope) {
        New-ManagementScope -Name $ScopeName -RecipientRestrictionFilter $scopeFilter | Out-Null
    }
    elseif ($existingScope.RecipientFilter -notlike "*$Mailbox*") {
        throw "Existing management scope does not match the requested mailbox. Refusing to broaden or replace it automatically."
    }

    $assignmentName = "$DisplayName - Application Mail.Read"
    $existingAssignment = Get-ManagementRoleAssignment -Identity $assignmentName -ErrorAction SilentlyContinue
    if (-not $existingAssignment) {
        New-ManagementRoleAssignment -Name $assignmentName -App $ServicePrincipalObjectId -Role "Application Mail.Read" -CustomResourceScope $ScopeName | Out-Null
    }

    $test = Test-ServicePrincipalAuthorization -Identity $ServicePrincipalObjectId -Resource $Mailbox
    $mailRead = $test | Where-Object { $_.RoleName -eq "Application Mail.Read" }

    [pscustomobject]@{
        AppId = $AppId
        ServicePrincipalObjectId = $ServicePrincipalObjectId
        Mailbox = $Mailbox
        ScopeName = $ScopeName
        Role = "Application Mail.Read"
        InScope = [bool]($mailRead.InScope)
        GrantedPermissions = ($mailRead.GrantedPermissions -join ",")
        Status = if ($mailRead.InScope) { "PASS" } else { "FAIL" }
    } | Format-List

    if (-not $mailRead.InScope) {
        throw "Exchange Application RBAC test did not confirm the mailbox is in scope."
    }
}
finally {
    Disconnect-ExchangeOnline -Confirm:$false
}
