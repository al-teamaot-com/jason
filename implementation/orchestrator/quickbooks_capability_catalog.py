from __future__ import annotations

from datetime import datetime

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)

QUICKBOOKS_PROVIDER = "quickbooks"

ACCOUNTING_COMPANY_READ = "accounting.company.read"
ACCOUNTING_ACCOUNT_SEARCH = "accounting.account.search"
ACCOUNTING_VENDOR_SEARCH = "accounting.vendor.search"
ACCOUNTING_CUSTOMER_SEARCH = "accounting.customer.search"
ACCOUNTING_INVOICE_SEARCH = "accounting.invoice.search"
ACCOUNTING_BILL_SEARCH = "accounting.bill.search"
ACCOUNTING_PROFIT_LOSS_READ = "accounting.report.profit_loss.read"
ACCOUNTING_BALANCE_SHEET_READ = "accounting.report.balance_sheet.read"

QUICKBOOKS_CAPABILITIES = frozenset(
    {
        ACCOUNTING_COMPANY_READ,
        ACCOUNTING_ACCOUNT_SEARCH,
        ACCOUNTING_VENDOR_SEARCH,
        ACCOUNTING_CUSTOMER_SEARCH,
        ACCOUNTING_INVOICE_SEARCH,
        ACCOUNTING_BILL_SEARCH,
        ACCOUNTING_PROFIT_LOSS_READ,
        ACCOUNTING_BALANCE_SHEET_READ,
    }
)


def _read_capability(
    *,
    now: datetime,
    name: str,
    display_name: str,
    purpose: str,
    resource_types: str,
    operation: str,
    selector_keys: str,
    fact_hints: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.PILOT,
        business_purpose=purpose,
        owner_service="Jason Accounting Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal", "financial"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "OAuth-bound QuickBooks Realm ID"),
            verification_requirements=(
                "Realm ID is derived only from the completed OAuth connection",
                "Accounting scope is the only requested Intuit scope",
                "connector environment matches the OAuth connection environment",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior=(
            "Fail closed without raw query, caller-supplied Realm ID, browser, "
            "shell, or ungoverned provider fallback."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Provide governed read-only QuickBooks Online accounting evidence "
                "for AOT reconciliation and financial operations."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "QuickBooks Online is no longer AOT's approved accounting authority.",
                "A replacement satisfies the canonical accounting read contracts.",
            ),
            authoritative_change_sources=(
                "Intuit QuickBooks Online Accounting API documentation",
                "Intuit OAuth 2.0 documentation",
                "Intuit Developer Terms of Service",
            ),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": resource_types,
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": fact_hints,
            "scope_model": "aot_internal_single_quickbooks_company",
            "company_scope_enforced_by": "oauth_realm_binding",
            "financial_data": "true",
        },
    )


def quickbooks_capabilities(now: datetime) -> tuple[CapabilityDefinition, ...]:
    return (
        _read_capability(
            now=now,
            name=ACCOUNTING_COMPANY_READ,
            display_name="Read Accounting Company",
            purpose="Read identity and configuration for the OAuth-authorized QuickBooks company.",
            resource_types="accounting_company",
            operation="read",
            selector_keys="",
            fact_hints="QuickBooks company accounting books company info",
        ),
        _read_capability(
            now=now,
            name=ACCOUNTING_ACCOUNT_SEARCH,
            display_name="Search Accounting Accounts",
            purpose="Search the chart of accounts in the OAuth-authorized QuickBooks company.",
            resource_types="accounting_account",
            operation="search",
            selector_keys="start_position,max_results",
            fact_hints="chart of accounts account asset liability income expense",
        ),
        _read_capability(
            now=now,
            name=ACCOUNTING_VENDOR_SEARCH,
            display_name="Search Accounting Vendors",
            purpose="Search vendors in the OAuth-authorized QuickBooks company.",
            resource_types="accounting_vendor",
            operation="search",
            selector_keys="start_position,max_results",
            fact_hints="vendor supplier payee accounts payable",
        ),
        _read_capability(
            now=now,
            name=ACCOUNTING_CUSTOMER_SEARCH,
            display_name="Search Accounting Customers",
            purpose="Search customers in the OAuth-authorized QuickBooks company.",
            resource_types="accounting_customer",
            operation="search",
            selector_keys="start_position,max_results",
            fact_hints="customer client accounts receivable",
        ),
        _read_capability(
            now=now,
            name=ACCOUNTING_INVOICE_SEARCH,
            display_name="Search Accounting Invoices",
            purpose="Search invoices in the OAuth-authorized QuickBooks company.",
            resource_types="accounting_invoice",
            operation="search",
            selector_keys="start_position,max_results",
            fact_hints="invoice receivable billing customer balance",
        ),
        _read_capability(
            now=now,
            name=ACCOUNTING_BILL_SEARCH,
            display_name="Search Accounting Bills",
            purpose="Search bills in the OAuth-authorized QuickBooks company.",
            resource_types="accounting_bill",
            operation="search",
            selector_keys="start_position,max_results",
            fact_hints="bill payable vendor expense due balance",
        ),
        _read_capability(
            now=now,
            name=ACCOUNTING_PROFIT_LOSS_READ,
            display_name="Read Profit and Loss Report",
            purpose="Read a bounded QuickBooks Profit and Loss report.",
            resource_types="accounting_report",
            operation="read",
            selector_keys="start_date,end_date",
            fact_hints="profit loss income statement revenue expense net income",
        ),
        _read_capability(
            now=now,
            name=ACCOUNTING_BALANCE_SHEET_READ,
            display_name="Read Balance Sheet Report",
            purpose="Read a bounded QuickBooks Balance Sheet report.",
            resource_types="accounting_report",
            operation="read",
            selector_keys="start_date,end_date",
            fact_hints="balance sheet assets liabilities equity",
        ),
    )


def quickbooks_provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=QUICKBOOKS_PROVIDER,
        display_name="QuickBooks Online Accounting API",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=QUICKBOOKS_CAPABILITIES,
        supported_classifications=frozenset({"internal", "financial"}),
        regions=frozenset({"US"}),
        limits=ProviderLimits(
            maximum_concurrent_executions=3,
            maximum_requests_per_minute=30,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "QuickBooks Online is AOT's authoritative accounting data source."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "QuickBooks Online is no longer AOT's approved accounting authority.",
                "A replacement satisfies the canonical accounting read contracts.",
            ),
            vendor_change_sources=(
                "Intuit QuickBooks Online Accounting API documentation",
                "Intuit OAuth 2.0 documentation",
                "Intuit Developer Terms of Service",
            ),
            operational_owner="AOT Finance / Managed Services",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": QUICKBOOKS_PROVIDER,
            "resource_authority": "aot_accounting",
            "live_enablement": "blocked_pending_explicit_quickbooks_profile",
            "oauth_scope": "com.intuit.quickbooks.accounting",
        },
    )


def register_quickbooks_read_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    for capability in quickbooks_capabilities(now):
        capabilities.register(capability)
    providers.register(quickbooks_provider(now))
