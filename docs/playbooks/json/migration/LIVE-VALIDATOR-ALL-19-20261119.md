# 19 JSON source candidates — live Jason validator confirmation

## Verification scope
All 19 canonical JSON source payloads were submitted individually to Jason’s connected `validate_json_playbook` governed non-storing API on November 19, 2026. Each returned `status=valid` with the exact version and canonical immutable fingerprint expected by the source ledger. The validation tool explicitly does **not** stage, activate, dispatch, or run the playbooks.

| Legacy playbook | JSON version | Fingerprint | Live validator |
|---|---|---|---|
| `backupiq_endpoint_backup` | `1.3.0-migration.2` | `18d2ab42682ac126e346b9d34adb758e1340e8b9f28edc647de348d435906562` | valid |
| `datto_edr_av` | `1.3.0-migration.2` | `08cca798a22392ad71c94ce95a49ff988c735a30a6e9d13c982b9676c95d967c` | valid |
| `disk_bad_block_event_7` | `1.0.0-migration.2` | `6bde35361a6732af1dd75e6ffe4ceef86f8a96ca91079a577a1edebb414ac427` | valid |
| `dns_agent_diagnostic` | `1.0.0-migration.2` | `a0f12074057afef7a1583a0f0f849ce88aef3980ec1bf96051df73d3b6b17a55` | valid |
| `drmm_recent_alert_reconciliation` | `1.0.0-migration.1` | `53753e4f1d69f243f614c52b82de44384626a06e16d3686b0762c99127507055` | valid |
| `gpt_insights_tech_assist` | `0.2.1-migration.2` | `2f7f8c15d3e233284270e55a38a838cf7a09ff11ddc1c08ef81a2915e280fe51` | valid |
| `idle_log_off` | `1.1.0-migration.2` | `6520da707d310448b15de77d01b4fbc92e5fdaaf7c4156c83297737665884cf4` | valid |
| `jason_activity_log` | `1.0.0-migration.2` | `84755d1fc0bccc58ca34dd27dcb536ebd47d03a6d0aee95a2c8bb40137dccdb6` | valid |
| `low_disk_space` | `1.1.0-migration.2` | `8ddfe6f27137480d72b22e750ad9b1b8953e1cd73309b73a46ab12b632622959` | valid |
| `offline_ticket_context_augmentation` | `0.1.0-migration.2` | `feeb7e6e0379487f65906a712d1955d1e7da97769ce6a57aaaa17a91f82dd698` | valid |
| `post_error_investigation` | `1.0.0-migration.2` | `6d93920c32e13583c40a74fee13d31d72dc7d2c7f3744a645836d390a0b2f9cc` | valid |
| `security_log_self_heal` | `1.0.0-migration.2` | `76e458c394689a153fb43bfd3b911b341324528231344058e9811f5e1f7ca959` | valid |
| `unexpected_shutdown` | `1.1.0-migration.2` | `c23b8ed6c8091e291704daa5ec18a2696715af6a89780f0030d8d6efd1f40e61` | valid |
| `vulscan_missing_patch` | `1.1.0-migration.2` | `a486a0561d85d6fa3b3af90f61512ea6b43d927d5f0670ba79fe2c1bcdb44022` | valid |
| `vulscan_multi_device_split` | `1.0.0-migration.2` | `c3b693dd1d5ee17309a8281ef21d3cee5ccad4893e5c0f9f6fa7062a3c6ab318` | valid |
| `windows_time_source` | `0.1.0-migration.1` | `b75a183d829f7cb98c4b53a8813919e47ece77698d4fd8d6a5a8ee98ea983b44` | valid |
| `client_information_request` | `1.0.0-migration.2` | `a1848fe643728391707e1dc35096811cffcc7749d49738835ca0ae4d193430f5` | valid |
| `unsupported_readonly_triage_note` | `1.0.0-migration.1` | `d0b54b17155b7126226242d462ccb8db3180654a244a5ce92ab8e1bb219f7ad7` | valid |
| `unsupported_triage_human_review` | `1.0.0-migration.1` | `5c8388351ff72d0cbe8e8bac7950c8b99f27bff310f61ff7ae7c2197ade2c662` | valid |

## Safety and limits

- This is deployed-schema and semantic compatibility via Jason’s production validator. It is **not** autonomous execution, runtime-to-live provider integration, synthetic source classifier parity for all branches, complete job retry/recovery, or real environment preproduction acceptance.
- The test-only source registry staged 19 drafts in a separate temporary SQLite database and verified zero active versions and unchanged source fingerprint on restart. No production JSON stage/activation was requested.
- The candidate source authority gate separately checks original legacy registry write allowances. Provider actions and promotions remain **ungranted**.
- All 19 authored playbooks retain open gaps in `ALL-19-ACCEPTANCE-MATRIX.md`; none is independently fully accepted or production-active.

## Outcome
**Live non-storing Jason JSON validation: 19/19 PASS. Full behavioral parity: 0/19 accepted. Live provider-backed autonomous preproduction acceptance: 0/19 accepted. Production activation/legacy retirement: none.**
