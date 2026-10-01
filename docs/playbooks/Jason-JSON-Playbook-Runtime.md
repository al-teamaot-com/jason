# Jason JSON Playbook Runtime

## Section Goal

Allow Project Jason playbooks to be authored, validated, versioned, staged, activated, retired, and interpreted as runtime data without rebuilding or restarting Jason for each playbook change.

Success requires:
- immutable versioned JSON definitions;
- schema plus semantic validation;
- deterministic step/branch interpretation;
- no inline shell/provider bypass;
- capability references resolved against Jason's registered capability catalog;
- durable runtime storage outside the application image;
- activation/retirement without service reload;
- no authority created by JSON activation;
- existing Jason governance remains authoritative.

## Architecture

The runtime separates three concerns:

1. Playbook JSON describes procedure.
2. Jason capability registry/orchestrator provides governed operations.
3. Jason identity, approval and policy controls determine execution authority.

A JSON playbook can request a capability but cannot create a grant, bypass an approval, invoke a provider directly, or weaken disruptive-action protections.

## Lifecycle

validate -> stage(draft) -> activate -> retire

Staging is immutable by (playbook_id, version). Editing a staged/active version requires a new semantic version.

Activation swaps the active version in the durable registry and increments the registry generation. Consumers read the active snapshot/generation at runtime; no process restart is required.

## Runtime administration

The MCP control plane exposes:
- validate_json_playbook
- stage_json_playbook
- list_json_playbooks
- activate_json_playbook
- retire_json_playbook

Validation and staging create no execution authority. Activation is owner-governed in v1 and also creates no provider authority. Existing exact capability grants, autonomy promotion, approval binding, client isolation, and Central Orchestrator controls remain required before a declared action can execute.

## Migration rule

Existing Markdown/code playbooks continue to operate until migrated. Migration is incremental:

1. create a new JSON version using the canonical standard playbook template;
2. validate and stage it;
3. run shadow/dry-run acceptance against a controlled ticket/device;
4. activate the exact version;
5. separately promote any autonomous branches under existing governance;
6. retire the legacy implementation only after parity is demonstrated.

Do not bulk-convert all existing playbooks without per-playbook acceptance.

## V1 limitations

The v1 interpreter is intentionally bounded. It supports deterministic ordered steps, finite decisions, bounded retries, wait/recheck declarations, capability calls, explicit verification steps, and terminal outcomes. Arbitrary code, inline PowerShell/shell, dynamic provider URLs, and direct-provider execution are prohibited.

The first production migration should be one existing low-risk playbook in shadow mode. This proves matching, state persistence, capability resolution, documentation, verification, and rollback before broader migration.

## Documentation impact

This runtime adds a new machine-readable playbook representation and administration surface while preserving the existing canonical Markdown playbooks during incremental migration.

Activation changes registry state only; separate Jason authority remains mandatory for every governed capability execution.
