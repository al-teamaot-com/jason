$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Result {
    param(
        [bool]$Ok,
        [object]$Data,
        [string]$ErrorCode
    )
    if ($Ok) {
        @{ ok = $true; data = $Data } | ConvertTo-Json -Depth 10 -Compress
    } else {
        @{ ok = $false; error_code = $ErrorCode } | ConvertTo-Json -Depth 4 -Compress
    }
}

function Require-Mailbox {
    param([object]$Arguments)
    $mailbox = [string]$Arguments.mailbox
    if ([string]::IsNullOrWhiteSpace($mailbox) -or $mailbox -notmatch '^[^@\s]+@[^@\s]+$') {
        throw "INVALID_MAILBOX"
    }
    return $mailbox.Trim()
}

try {
    $raw = [Console]::In.ReadToEnd()
    $request = $raw | ConvertFrom-Json -Depth 10

    $allowedOperations = @(
        "message_trace.search",
        "message_trace.detail",
        "mailbox.forwarding.read",
        "mailbox.inbox_rules.read_hidden",
        "mailbox.full_access.read",
        "mailbox.send_as.read",
        "mailbox.send_on_behalf.read",
        "mailbox.transport_rules.read",
        "mailbox.mobile_devices.read",
        "mailbox.retention_audit_config.read"
    )
    if ($request.operation -notin $allowedOperations) {
        throw "OPERATION_NOT_ALLOWED"
    }

    $appId = [string]$env:JASON_EXCHANGE_APP_ID
    $certificatePath = [string]$env:JASON_EXCHANGE_CERTIFICATE_PFX
    $passwordPath = [string]$env:JASON_EXCHANGE_CERTIFICATE_PASSWORD_FILE
    if (
        [string]::IsNullOrWhiteSpace($appId) -or
        [string]::IsNullOrWhiteSpace($certificatePath) -or
        [string]::IsNullOrWhiteSpace($passwordPath)
    ) {
        throw "WORKER_CREDENTIAL_CONFIGURATION_MISSING"
    }

    $certificatePassword = (Get-Content -LiteralPath $passwordPath -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($certificatePassword)) {
        throw "WORKER_CERTIFICATE_PASSWORD_MISSING"
    }
    $securePassword = ConvertTo-SecureString -String $certificatePassword -AsPlainText -Force

    $commandNames = @(
        "Get-MessageTraceV2",
        "Get-MessageTraceDetailV2",
        "Get-Mailbox",
        "Get-Recipient",
        "Get-InboxRule",
        "Get-EXOMailboxPermission",
        "Get-EXORecipientPermission",
        "Get-TransportRule",
        "Get-MobileDevice",
        "Get-EXOMobileDeviceStatistics"
    )

    $connectParameters = @{
        AppId = $appId
        CertificateFilePath = $certificatePath
        CertificatePassword = $securePassword
        Organization = [string]$request.organization
        CommandName = $commandNames
        ShowBanner = $false
        ShowProgress = $false
    }
    Connect-ExchangeOnline @connectParameters | Out-Null

    $arguments = $request.arguments
    $items = @()

    switch ([string]$request.operation) {
        "message_trace.search" {
            $start = [DateTimeOffset]::Parse([string]$arguments.start).UtcDateTime
            $end = [DateTimeOffset]::Parse([string]$arguments.end).UtcDateTime
            if ($end -le $start) { throw "INVALID_TRACE_WINDOW" }

            $traceParameters = @{
                StartDate = $start
                EndDate = $end
                ResultSize = if ($arguments.result_size) { [int]$arguments.result_size } else { 5000 }
            }
            if ($traceParameters.ResultSize -lt 1 -or $traceParameters.ResultSize -gt 5000) {
                throw "INVALID_RESULT_SIZE"
            }
            if ($arguments.sender) {
                $traceParameters.SenderAddress = [string]$arguments.sender
            }
            if ($arguments.recipients) {
                $traceParameters.RecipientAddress = @($arguments.recipients | ForEach-Object { [string]$_ })
            }
            if ($arguments.subject) {
                $traceParameters.Subject = [string]$arguments.subject
                $traceParameters.SubjectFilterType = "Contains"
            }

            $items = @(Get-MessageTraceV2 @traceParameters | Select-Object Received,SenderAddress,RecipientAddress,Status,Subject,MessageTraceId,MessageId)
        }

        "message_trace.detail" {
            $traceId = [string]$arguments.message_trace_id
            $recipient = [string]$arguments.recipient
            if ([string]::IsNullOrWhiteSpace($traceId) -or [string]::IsNullOrWhiteSpace($recipient)) {
                throw "TRACE_DETAIL_ARGUMENTS_REQUIRED"
            }
            $items = @(Get-MessageTraceDetailV2 -MessageTraceId $traceId -RecipientAddress $recipient | Select-Object Date,Event,Action,Detail,Data,MessageId,MessageTraceId,RecipientAddress)
        }

        "mailbox.forwarding.read" {
            $mailbox = Require-Mailbox $arguments
            $items = @(Get-Mailbox -Identity $mailbox | Select-Object DisplayName,PrimarySmtpAddress,RecipientTypeDetails,ForwardingAddress,ForwardingSmtpAddress,DeliverToMailboxAndForward)
        }

        "mailbox.inbox_rules.read_hidden" {
            $mailbox = Require-Mailbox $arguments
            $items = @(Get-InboxRule -Mailbox $mailbox -IncludeHidden | Select-Object Name,Enabled,Priority,Description,MoveToFolder,CopyToFolder,DeleteMessage,SoftDeleteMessage,RedirectTo,ForwardTo,ForwardAsAttachmentTo,StopProcessingRules)
        }

        "mailbox.full_access.read" {
            $mailbox = Require-Mailbox $arguments
            $items = @(Get-EXOMailboxPermission -Identity $mailbox | Where-Object {
                $_.User -notmatch "NT AUTHORITY\\SELF" -and $_.AccessRights -contains "FullAccess"
            } | Select-Object User,AccessRights,Deny,IsInherited)
        }

        "mailbox.send_as.read" {
            $mailbox = Require-Mailbox $arguments
            $items = @(Get-EXORecipientPermission -Identity $mailbox | Where-Object {
                $_.Trustee -notmatch "NT AUTHORITY\\SELF"
            } | Select-Object Trustee,AccessRights)
        }

        "mailbox.send_on_behalf.read" {
            $mailbox = Require-Mailbox $arguments
            $mbx = Get-Mailbox -Identity $mailbox
            $items = @($mbx.GrantSendOnBehalfTo | ForEach-Object {
                [PSCustomObject]@{ Identity = [string]$_ }
            })
        }

        "mailbox.transport_rules.read" {
            $items = @(Get-TransportRule | Select-Object Name,State,Priority,Mode,SetSCL,SetHeaderName,SetHeaderValue,StopRuleProcessing)
        }

        "mailbox.mobile_devices.read" {
            $mailbox = Require-Mailbox $arguments
            $items = @(Get-EXOMobileDeviceStatistics -Mailbox $mailbox | Select-Object DeviceType,DeviceModel,DeviceOS,DeviceUserAgent,DeviceAccessState,DeviceAccessStateReason,LastSuccessSync,LastSyncAttemptTime,FirstSyncTime,DeviceId)
        }

        "mailbox.retention_audit_config.read" {
            $mailbox = Require-Mailbox $arguments
            $items = @(Get-Mailbox -Identity $mailbox | Select-Object RetentionPolicy,RetentionHoldEnabled,LitigationHoldEnabled,ArchiveStatus,AuditEnabled,AuditLogAgeLimit,DefaultAuditSet,AuditOwner,AuditDelegate,AuditAdmin)
        }
    }

    $normalized = @($items | ForEach-Object {
        $row = [ordered]@{}
        foreach ($property in $_.PSObject.Properties) {
            $value = $property.Value
            if ($null -eq $value) {
                $row[$property.Name] = $null
            } elseif ($value -is [System.Collections.IEnumerable] -and $value -isnot [string]) {
                $row[$property.Name] = @($value | ForEach-Object { [string]$_ })
            } else {
                $row[$property.Name] = [string]$value
            }
        }
        [PSCustomObject]$row
    })

    Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Write-Result -Ok $true -Data @{
        operation = [string]$request.operation
        correlation_id = [string]$request.correlation_id
        items = $normalized
        count = $normalized.Count
    }
    exit 0
}
catch {
    Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    $message = [string]$_.Exception.Message
    $code = switch -Regex ($message) {
        '^INVALID_' { $message; break }
        '^OPERATION_' { $message; break }
        '^TRACE_' { $message; break }
        '^WORKER_' { $message; break }
        default { "EXCHANGE_READ_OPERATION_FAILED" }
    }
    Write-Result -Ok $false -Data $null -ErrorCode $code
    exit 0
}
