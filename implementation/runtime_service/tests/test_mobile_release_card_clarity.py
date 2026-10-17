"""A phone owner sees the real two-button release card, not a generic status alert."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from connectors.microsoft_graph.teams_approval_channel import TeamsApprovalCard
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
from jason_runtime.autonomous_completion_notification import _render

SHA = "4c53757a3dfcb097309c6738f5ef045a8adabb37"
ROLLBACK = "5277d29318c5ce31160ccb56055a8f83eb7bf4a9"


def card(capability="release.production.approve", approval_id="relapproval-test"):
    return TeamsApprovalCard(
        approval_id=approval_id, organization_id="aot",
        title="Production + CCC: Documentation-only change",
        summary="Review this exact immutable release before deployment",
        capability=capability, requested_mode="release:" + SHA,
        expires_at="2026-10-17T12:02:42Z",
        evidence_artifact_ids=(),
        facts=(
            ("Release", "release-" + SHA[:16]),
            ("Exact SHA", SHA),
            ("Purpose", "Documentation-only change"),
            ("Highest risk", "normal"),
            ("Affected services", "runtime, mcp, scheduled controls"),
            ("Changed files", "docs/control/state.json"),
            ("Rollback", ROLLBACK),
            ("Preproduction and rollback", "Passed"),
            ("Release policy", "sha256:"+"a"*64),
            ("Manifest fingerprint", "b"*64),
        ),
    )


def test_mobile_release_card_has_two_accessible_buttons_and_key_details():
    result = TeamsGatewayPlaybookApprovalSender._adaptive_card(card())
    assert result["type"] == "AdaptiveCard"
    assert result["version"] == "1.4"
    assert result["body"][0]["text"] == "ACTION REQUIRED: PRODUCTION + CCC"
    assert [x["title"] for x in result["actions"]] == ["Approve", "Deny"]
    assert [x["data"]["decision"] for x in result["actions"]] == ["approve", "deny"]
    assert all(x["data"]["approval_id"] == "relapproval-test" for x in result["actions"])
    facts = result["body"][-1]["facts"]
    assert len(facts) <= 9
    vals = [x["value"] for x in facts]
    assert SHA in vals
    assert ROLLBACK in vals
    assert "docs/control/state.json" in vals
    assert "runtime, mcp, scheduled controls" in vals
    assert "b"*64 in vals
    assert "normal" in vals
    assert not any(f["title"] in {"Approval ID", "Capability", "Mode"} for f in facts)
    assert "Request Changes" not in str(result)


def test_teams_gateway_accepts_both_mobile_card_actions():
    result = TeamsGatewayPlaybookApprovalSender._adaptive_card(card())
    root = Path(__file__).resolve().parents[3]
    module = root / "infrastructure/jason-teams-gateway/approval-submit.mjs"
    if not module.exists():
        root = root.parent
        module = root / "infrastructure/jason-teams-gateway/approval-submit.mjs"
    script = (
        "import { parseApprovalSubmit } from " + json.dumps(module.as_uri()) +
        '; let s=""; for await (const c of process.stdin) s+=c;'
        " console.log(JSON.stringify(JSON.parse(s).map(parseApprovalSubmit)));"
    )
    parsed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps([x["data"] for x in result["actions"]]),
        capture_output=True, text=True, check=True, timeout=12,
    )
    values = json.loads(parsed.stdout)
    assert [x["decision"] for x in values] == ["approve", "deny"]
    assert all(x["approvalId"] == "relapproval-test" for x in values)
    assert all(not x["selections"] for x in values)


def test_other_playbook_approval_cards_remain_unchanged():
    result = TeamsGatewayPlaybookApprovalSender._adaptive_card(
        card(capability="playbook.autonomy.promote", approval_id="pbautreq-test")
    )
    assert [a["title"] for a in result["actions"]] == [
        "Approve", "Deny", "Request Changes",
    ]
    assert result["body"][0]["text"].startswith("Production + CCC:")
    assert len(result["body"][-1]["facts"]) >= 14


def test_old_release_notice_prominently_identifies_itself_as_status_only():
    event, text, rendered = _render({
        "event_type": "production_owner_action_required",
        "work_id": "release-" + SHA[:16],
        "summary": "Documentation-only change",
        "candidate_sha": SHA,
        "owner_action": "Owner approval is required to promote this build to Production.",
    })
    assert event == "production_owner_action_required"
    assert "STATUS ONLY" in text
    assert "no approval buttons" in text.lower()
    assert "NOT an approval card" in rendered["body"][0]["text"]
    assert "no approval buttons" in rendered["body"][1]["text"].lower()
    assert not rendered.get("actions")
