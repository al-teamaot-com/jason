"""Deliver Root-sealed review through the existing bot, never a caller's card.

Only the installed Root worker calls send(). The existing Teams gateway owns
the Microsoft credential and SDK. No new OAuth client or private signing key.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import urllib.request

from tools.pmv4_teams_objective_admission import canonical, need, timestamp


def review(enrollment):
    scope = enrollment["material"]["scope"]
    steps = enrollment["material"]["requests"]
    facts = [
        {"title": "Plan fingerprint", "value": enrollment["plan_fingerprint"]},
        {"title": "Production impact", "value": "Restore the reviewed documentation publisher override; run and verify its existing scheduled job."},
        {"title": "Excluded", "value": "Runtime, MCP, Ticket Core, provider data, freeze and promotion hold changes."},
        {"title": "Expiry", "value": scope["expires_at"]},
    ]
    for index, step in enumerate(steps, 1):
        args = step["arguments"]
        facts.extend([
            {"title": "Step " + str(index), "value": step["capability_name"]},
            {"title": "Candidate / rollback", "value": args["candidate_sha"] + " / " + args["rollback_sha"]},
            {"title": "Exact scope / manifest", "value": args["scope_sha256"] + " / " + args["manifest_sha256"]},
        ])
    return {
        "aadObjectId": "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
        "tenantId": "f7054323-d52b-4863-8c2f-1898f0b6077c",
        "text": "One Owner decision: complete the reviewed documentation restoration and verification.",
        "card": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard", "version": "1.4",
            "body": [
                {"type": "TextBlock", "text": "APPROVAL REQUIRED: COMPLETE DEFINED OBJECTIVE",
                 "weight": "Bolder", "wrap": True},
                {"type": "TextBlock", "text": "Restore documentation publishing and verify the scheduled job",
                 "weight": "Bolder", "wrap": True},
                {"type": "TextBlock", "wrap": True,
                 "text": "Approve once for both exact steps and their covered readback/recovery. Independent safety and release checks remain required. A failed or unknown action is never blindly repeated."},
                {"type": "FactSet", "facts": facts}],
            "actions": [{"type": "Action.Submit", "title": title,
                "data": {"approval_id": enrollment["approval_id"], "decision": decision,
                         "card_challenge": enrollment["card_instance_challenge"]}}
                for title, decision in (("Approve", "approve"), ("Deny", "deny"))]},
    }


def send(enrollment, config, native):
    need(datetime.now(timezone.utc) < timestamp(enrollment["material"]["scope"]["expires_at"]),
         "CARD_EXPIRED_BEFORE_DELIVERY")
    need(config["teams_gateway_url"] == "http://127.0.0.1:3978", "FIXED_TEAMS_GATEWAY_REQUIRED")
    token = native["read"](Path("/var/lib/jason/openclaw/teams-proactive-token"), 1000, 0o600)
    need(sha256(token).hexdigest() == config["teams_token_sha256"], "TEAMS_TRANSPORT_CHANGED")
    request = urllib.request.Request(
        config["teams_gateway_url"] + "/internal/proactive/send", data=canonical(review(enrollment)),
        headers={"Authorization": "Bearer " + token.decode().strip(), "Content-Type": "application/json"},
        method="POST")
    # Do not follow redirects carrying the existing bot's service credential.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(request, timeout=35) as response:
        need(response.status == 200, "TEAMS_PROVIDER_DELIVERY_FAILED")
        raw = response.read(65537)
    need(len(raw) <= 65536, "TEAMS_DELIVERY_RESPONSE_OVER_LIMIT")
    result = json.loads(raw)
    message = result.get("message_id")
    need(result.get("status") == "succeeded" and result.get("channel") == "microsoft_teams"
         and result.get("message_id_synthetic") is False
         and isinstance(message, str) and 0 < len(message) <= 256
         and not message.startswith("accepted:") and not any(c.isspace() for c in message),
         "REAL_TEAMS_PROVIDER_MESSAGE_REQUIRED")
    return message
