# Jason Autonomous Ticket Activity Reporting

## Purpose

Jason must be able to answer operational questions such as "what tickets did you work last night?" from durable Jason-owned evidence even when Autotask search is temporarily unavailable.

## Durable evidence

`SQLiteOperationalWorkStore` maintains an append-only `autonomy_ticket_activity` ledger in the autonomy worker database. Each persisted work transition records only bounded operational metadata:

- Autotask ticket ID and ticket number
- ticket title
- playbook ID
- source queue
- work phase
- bounded reason text already persisted by the worker
- UTC activity timestamp

The ledger does not store provider credentials, raw provider payloads, or ticket-note bodies.

On first initialization after this feature is deployed, the store seeds at most the latest existing persisted state for each current work row using its already-durable `updated_at` timestamp. This provides bounded migration evidence without inventing historical transitions.

## Read surface

The MCP tool `jason_ticket_activity_report` accepts exact timezone-aware ISO-8601 `start_time` and `end_time` values and returns one aggregated record per ticket worked in that interval, including:

- first and last activity timestamps
- initial and last queue
- initial and last phase
- phases observed during the window
- last bounded reason
- activity event count

The report reads the local durable ledger in SQLite read-only/query-only mode. It is provider-independent and therefore does not depend on a live Autotask search succeeding.

The maximum report window is 31 days and the maximum returned ticket count is 500.

## Operational use

For overnight reporting, resolve the requested local-time window to exact offset-aware timestamps before calling the tool. The report is authoritative for Jason worker activity recorded after the ledger feature became active. Migrated pre-feature rows represent only the latest previously persisted timestamp/state and must not be described as a complete historical transition sequence.
