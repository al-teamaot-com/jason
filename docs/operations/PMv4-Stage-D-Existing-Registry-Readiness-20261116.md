# PMv4 Stage D — reuse the live JSON playbook registry, no second registry

**Status:** Live read-only inspection and isolated-copy upgrade acceptance PASS.
A separately hosted Runbook Management lifecycle is **NOT** installed.

## Authoritative actual state — November 16, 2026

- Existing production JSON source: `/var/lib/jason/openclaw/json-playbooks.sqlite3`, UID 1000, mode `0600`. No new DB or alternate registry is authorized.
- Live SQLite integrity `PRAGMA quick_check=ok`, generation 0, zero staged or active definitions.
- The live file has `json_playbooks` and `json_playbook_registry_meta`, but not the newer `json_playbook_lifecycle_events` schema required for actor/fingerprint/generation lifecycle audit. A source-only test with newly created databases is not proof that this live schema is ready.
- Current `SQLitePlaybookRegistry` already implements transactional stage, immutable version, activation, retirement, and generation+audit. Its constructor performs schema creation, so **do not open the live database with this constructor** outside a governed exact Owner transaction.
- A consistent SQLite backup made through `sqlite3.connect('file:...mode=ro')` into a disposable temporary file was upgraded using that existing registry. Synthetic stage, activate and retire advanced the **copied** generation from 0 to 3, produced three audit records, and `PRAGMA quick_check=ok`. The live database inode, size and mtime stayed unchanged.
- `tools/pmv4_runbook_registry_readback.py` makes these checks repeatable and fails closed on missing base schema, bad file modes, corrupt generation, duplicate active definitions, audit mismatch, a caller-chosen production path, or SQLite errors. Its default CLI reads only small aggregates. Its `--isolated-copy-acceptance` never writes to production, never mints Owner authority, and does not call providers.

## Required next component release

1. Bind the **existing single** SQLite registry path, source schema, historical backup, and exact authorized actor and capability policies to a separately reviewed D component release. Do not create a second playbook database or a second identity provider.
2. Implement and deploy an independently supervised Runbook Management control-plane service. The service must consume only already authenticated, scoped Jason actions from the existing Entra/MCP authorization boundary, never accept arbitrary local commands as execution authority, and never require PMv3 engineering/release to be running to operate.
3. Migrate the existing database schema in a native serialized transaction only after a consistent independent backup and exact rollback preparation. Preserve old definitions, generation, audit history and previously accepted legacy code/Markdown runbooks until each receives explicit parity acceptance.
4. With PM engineering paused in a controlled acceptance window, prove real governed stage/activate/readback/retire and hot-load across separate service processes; no code deploy or service restart; verify exact fingerprints, audit actor, generation, revocation and no new provider capability.
5. Independently verify native systemd/container service ownership, health/rollback, notification and MCP continuity. An inactive/source-only service is not operational D.
6. Keep production freeze/hold and the original ticket worker, MCP, signer and provider secrets untouched until the exact Owner release is authorized.

**Conclusion:** The existing registry is viable for a componentized D release; its live schema and independent service lifecycle still require governed installation. The source-only readback tool does not grant execution authority.
