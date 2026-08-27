# Provider Capability Readiness Monitoring

Status: Design foundation

## Purpose

Jason must know whether the systems and providers it depends on are operationally capable of performing the governed capabilities assigned to them.

This is different from ordinary process health.

A running container, reachable API endpoint, or valid credential does not prove that a provider can successfully execute the capability Jason requires.

Provider Capability Readiness Monitoring therefore exists to answer:

> Is Jason itself unhealthy, or is an external dependency preventing a governed capability from operating?

## Constitutional requirements

Provider readiness monitoring must follow Jason's existing architecture.

It must be:

- capability-driven rather than workflow-script-driven;
- provider-neutral above the connector/provider boundary;
- evidence-based;
- identity- and tenant-safe;
- auditable;
- bounded;
- non-destructive by default;
- independent from the user request path;
- safe when the monitoring system itself is unavailable.

Monitoring must not create a parallel execution authority.

It observes and classifies provider capability readiness.

## Four health dimensions

Every monitored provider capability should be capable of reporting four independent dimensions.

### 1. Component health

Question:

Is the Jason component required to use the provider itself running and healthy?

Examples:

- runtime process available;
- connector component loaded;
- required internal service available.

### 2. Dependency reachability

Question:

Can Jason reach the dependency?

Examples:

- DNS resolution;
- TCP/TLS establishment;
- API endpoint reachable.

### 3. Authentication readiness

Question:

Can Jason authenticate using the governed credential path?

Examples:

- OpenBao secret resolution;
- provider token acquisition;
- authenticated API request.

### 4. Capability readiness

Question:

Can the provider perform the actual bounded operation Jason requires?

This is the authoritative operational readiness check.

Examples:

- OpenAI can perform a minimal governed Responses API request;
- Microsoft Graph can perform a bounded read;
- Datto RMM can perform a bounded endpoint query;
- SES can perform the appropriate non-destructive readiness verification.

A successful authentication check alone is not sufficient.

## Canonical readiness states

Jason-owned provider readiness states:

- `HEALTHY`
- `DEGRADED`
- `UNAVAILABLE`
- `RECOVERING`
- `UNKNOWN`

Provider-specific status codes remain evidence and must be normalized into Jason-owned reason codes.

## Canonical reason codes

Initial reason vocabulary:

- `none`
- `runtime_unhealthy`
- `dependency_unreachable`
- `authentication_failed`
- `secret_unavailable`
- `permission_denied`
- `quota_exhausted`
- `rate_limited`
- `provider_timeout`
- `provider_unavailable`
- `contract_incompatible`
- `capability_probe_failed`
- `unknown_provider_failure`

This vocabulary should expand only when a materially distinct operational condition exists.

Do not encode vendor names or fact-specific request logic into the canonical classification.

## Evidence

Every readiness observation should retain safe evidence including:

- provider ID;
- capability name;
- observation time;
- readiness state;
- reason code;
- component health result;
- reachability result;
- authentication result;
- capability result;
- safe provider status code where applicable;
- evidence source;
- probe version.

Credentials, secrets, prompts, provider response bodies, and operational data values must not be stored in health evidence.

## State transitions

Alerts are transition-based.

Examples:

`HEALTHY -> UNAVAILABLE`

Immediate operational alert.

`UNAVAILABLE -> UNAVAILABLE`

Record fresh evidence but do not send duplicate immediate alerts.

`UNAVAILABLE -> RECOVERING`

Optional recovery-progress evidence.

`RECOVERING -> HEALTHY`

Recovery alert.

Repeated oscillation should be recognized as instability and may classify the provider as `DEGRADED`.

## Alert content

An alert should clearly distinguish:

- Jason runtime condition;
- provider condition;
- affected capability;
- normalized reason;
- operator action.

Example:

Provider capability unavailable

Provider: OpenAI Hosted Conversation Kernel
Capability: conversation.intent.interpret
Jason runtime: HEALTHY
Provider readiness: UNAVAILABLE
Reason: quota_exhausted
Evidence: HTTP 429 / credit_balance_exhausted
Action: restore provider API credit capacity

## Probe architecture

Provider-specific probes belong at the provider/connector boundary.

They return a provider-neutral readiness observation.

The readiness engine must not contain OpenAI-, Datto-, Microsoft-, Autotask-, or SES-specific branching.

Provider adapters translate their native result into the canonical observation contract.

## Probe safety

Readiness probes should be the least consequential operation capable of proving the real capability.

A reachability probe must not be mistaken for a capability-readiness probe.

Where possible probes should be:

- read-only;
- low cost;
- bounded;
- idempotent;
- rate limited;
- independently auditable.

If a capability cannot safely be actively probed, passive evidence may be used with an explicit freshness limit.

## Initial acceptance case

The 2026-08-24 OpenAI incident is the first acceptance case.

Given:

- Jason runtime healthy;
- OpenAI reachable;
- OpenAI authentication successful;
- Responses API returns HTTP 429;
- provider code is `credit_balance_exhausted`;

the readiness system must produce:

- provider readiness: `UNAVAILABLE`;
- reason: `quota_exhausted`;
- Jason runtime: `HEALTHY`;
- affected capabilities identified;
- one transition alert;
- no duplicate alert while state remains unchanged;
- recovery alert after capability execution succeeds again.

## Future monitored providers

The same architecture should be usable for:

- OpenAI hosted reasoning;
- OpenBao;
- Datto RMM;
- Microsoft Graph;
- Autotask;
- AWS SES;
- Ollama;
- IT Glue;
- other governed Jason providers and resources.

No separate monitoring framework should be created for each provider.
