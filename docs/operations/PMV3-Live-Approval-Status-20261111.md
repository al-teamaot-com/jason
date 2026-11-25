# PMV3 live release-approval status: never infer from stale engineering history

On November 11, 2026, the verified Teams-free release
`ee46ef631e04678a16f2543c76a8ee08ec974265` closed with
`mobile_release_approval_mode=owner_reviewed`, healthy runtime and MCP,
closed root circuit breaker, clean drift, and original production freeze
restored byte-for-byte.

The earlier PMV3 engineering controller report was last written November 4,
before the Teams-free cutover. It contained a hardcoded
`teams_only_approval=true`, which MCP mistakenly displayed as a live
policy fact. It was **historic run metadata**, not a current release gate.

The reporting fix:
- Removes the hardcoded approval-mode field from future PMV3 engineering
  controller state/output. That controller never issues Owner approval.
- Preserves any old value under
  `pmv3_engineering.historical_teams_only_approval` for audits.
- Uses `release_approval_policy` as the authoritative live status field,
  reading only root's protected last-known-good manifest and matching
  closed circuit breaker. When schema is `owner_reviewed`, it reports
  `teams_required=false`; missing, unexpected, open-breaker, or
  mismatched state returns **unknown**, never a guessed all-clear.
- Mirrors the current Teams requirement into the legacy
  `pmv3_engineering.teams_only_approval` compatibility field so older
  callers no longer confuse the November 4 result with today's production.
- Does not change the actual release policy, authentication,
  exact-action authorization, rollback, providers, ticket worker,
  notifications, production freeze, or circuit-breaker enforcement.

### Acceptance evidence and deployment boundary

The source regression tests exercise an old November PMV3 state with a
current Owner-reviewed LKG, missing PMV3 state, mismatched revisions, open
breaker, and unexpected approval modes. An isolated, read-only MCP image
loaded the live protected production readback and returned
`status=current,mode=owner_reviewed,teams_required=false` at the exact
deployed SHA. These tests do **not** mean this status-reporting change has
been deployed.

Only a separate governed release with its own exact authenticated Owner
authorization may replace the production MCP/status code. Do not hotpatch
containers, edit original historical state files, or disturb the verified
Teams-free release merely to change an indicator.

Operationally: **the release manager's protected LKG and current MCP
`release_approval_policy` field are the sources of truth for present
approvals; dated engineering artifacts are historical context.**

### Concurrent-change review

Reviewed overlap with #2384 (Constant Contact callback), #2343
(procurement quote/invoice), #2333 (gated security assessment), and #2305
(passive diagnostics) in the large MCP server module. Their source hunks
do not intersect this read-only PMV3 approval status function. Reviewed
#2296, which changes only PMV3 recoverable-failure classification and
does not touch the historical status field. This fix does not import,
reimplement or authorize any of those independent features.

Integration coordination: #2384 #2343 #2333 #2296 #2305 #2427 #2428 #2404 #2395 #2393 #2382 #2373
