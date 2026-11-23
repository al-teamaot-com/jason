"""Reloadable presentation/timing policy; never an authority or a new sender.

Only a trusted runtime composition may supply this path. Workflow facts come
from persisted requests. Existing signed callbacks and execution gates remain
authoritative, including when a new template is added without code changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


class TeamsConfigurationError(ValueError):
    pass


def _text(value: Any, maximum: int = 180) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise TeamsConfigurationError("nonempty bounded presentation text required")
    return value


def _keys(value: Any, expected: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise TeamsConfigurationError("unknown or missing configuration fields")


@dataclass(frozen=True)
class BusinessCalendar:
    zone: ZoneInfo
    weekdays: frozenset[int]
    opens: time
    closes: time
    holidays: frozenset[date]

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "BusinessCalendar":
        _keys(raw, {"timezone", "weekdays", "opens", "closes", "holidays"})
        days = raw["weekdays"]
        if (not isinstance(days, list) or not days or len(set(days)) != len(days)
                or any(type(d) is not int or d not in range(7) for d in days)):
            raise TeamsConfigurationError("invalid business weekdays")
        try:
            zone = ZoneInfo(raw["timezone"])
            opens, closes = time.fromisoformat(raw["opens"]), time.fromisoformat(raw["closes"])
            if not isinstance(raw["holidays"], list):
                raise ValueError("holiday list required")
            holidays = frozenset(date.fromisoformat(v) for v in raw["holidays"])
        except (ValueError, TypeError, KeyError) as exc:
            raise TeamsConfigurationError("invalid business calendar") from exc
        if opens.tzinfo or closes.tzinfo or opens >= closes or opens.second or closes.second:
            raise TeamsConfigurationError("same-day minute-precision business hours required")
        return cls(zone, frozenset(days), opens, closes, holidays)

    def is_open(self, instant: datetime) -> bool:
        self._aware(instant)
        local = instant.astimezone(self.zone)
        return (local.weekday() in self.weekdays and local.date() not in self.holidays
                and self.opens <= local.time() < self.closes)

    @staticmethod
    def _aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise TeamsConfigurationError("timezone-aware business clock required")

    def minutes_between(self, start: datetime, end: datetime) -> int:
        self._aware(start)
        self._aware(end)
        if end < start:
            raise TeamsConfigurationError("business clock moved backwards")
        first, last = start.astimezone(self.zone).date(), end.astimezone(self.zone).date()
        if (last - first).days > 3660:
            raise TeamsConfigurationError("business clock interval exceeds supported bound")
        seconds = 0.0
        current = first
        while current <= last:
            if current.weekday() in self.weekdays and current not in self.holidays:
                opening = datetime.combine(current, self.opens, self.zone).astimezone(timezone.utc)
                closing = datetime.combine(current, self.closes, self.zone).astimezone(timezone.utc)
                seconds += max(0, (min(end, closing) - max(start, opening)).total_seconds())
            current += timedelta(days=1)
        return int(seconds // 60)


@dataclass(frozen=True)
class TeamsWorkflowConfiguration:
    raw: Mapping[str, Any]
    calendar: BusinessCalendar
    digest: str

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "TeamsWorkflowConfiguration":
        _keys(raw, {"schema_version", "policy_version", "enabled", "calendar",
                    "reminder_business_minutes", "escalation_business_minutes",
                    "fallback_email", "events", "templates"})
        if raw["schema_version"] != "1.0" or type(raw["enabled"]) is not bool:
            raise TeamsConfigurationError("supported policy version and explicit enabled flag required")
        _text(raw["policy_version"])
        for key in ("reminder_business_minutes", "escalation_business_minutes"):
            if type(raw[key]) is not int or not 1 <= raw[key] <= 525600:
                raise TeamsConfigurationError("invalid business interval")
        if raw["reminder_business_minutes"] > raw["escalation_business_minutes"]:
            raise TeamsConfigurationError("reminder must precede escalation")
        fallback = _text(raw["fallback_email"], 254)
        if fallback.count("@") != 1 or any(c.isspace() for c in fallback):
            raise TeamsConfigurationError("fallback email required; identity authority is checked separately")
        allowed_events = {"approval_required", "reminder", "escalated", "completed",
                          "blocked", "denied", "cancelled", "restored"}
        if (not isinstance(raw["events"], list) or not raw["events"]
                or len(set(raw["events"])) != len(raw["events"])
                or set(raw["events"]) - allowed_events):
            raise TeamsConfigurationError("unknown or duplicate notification event")
        if not isinstance(raw["templates"], list) or not raw["templates"]:
            raise TeamsConfigurationError("template registry required")
        selectors = set()
        for template in raw["templates"]:
            _keys(template, {"capability", "mode", "title", "explanation", "primary", "details"})
            selector = (_text(template["capability"]), _text(template["mode"]))
            if selector in selectors:
                raise TeamsConfigurationError("ambiguous template selector")
            selectors.add(selector)
            _text(template["title"])
            _text(template["explanation"], 600)
            sources = []
            for group in ("primary", "details"):
                if not isinstance(template[group], list) or len(template[group]) > 30:
                    raise TeamsConfigurationError("bounded field list required")
                for field in template[group]:
                    _keys(field, {"source", "label", "required"})
                    sources.append(_text(field["source"], 120))
                    _text(field["label"], 120)
                    if type(field["required"]) is not bool:
                        raise TeamsConfigurationError("explicit required flag needed")
            if len(sources) != len(set(sources)):
                raise TeamsConfigurationError("duplicate template fact")
            if selector == ("procurement.submission.execute", "purchase"):
                primary = {f["source"] for f in template["primary"] if f["required"]}
                if not {"Submitted by", "Vendor", "Product", "Quantity", "Total Commitment"} <= primary:
                    raise TeamsConfigurationError("purchase template omits material purchase facts")
        content = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        # Detach the validated record from mutable caller input.
        return cls(json.loads(content), BusinessCalendar.parse(raw["calendar"]),
                   sha256(content.encode()).hexdigest())

    @property
    def enabled(self) -> bool:
        return self.raw["enabled"]

    @property
    def approval_scope_digest(self) -> str:
        # Presentation and reminder edits do not change a purchase's approved
        # business scope or force a second human decision. Routing changes do.
        return sha256(json.dumps({"schema_version": self.raw['schema_version'],
            "fallback_email": self.raw['fallback_email']}, sort_keys=True).encode()).hexdigest()

    def template(self, capability: str, mode: str) -> Mapping[str, Any] | None:
        return next((t for t in self.raw["templates"]
                     if (t["capability"], t["mode"]) == (capability, mode)), None)

    def due(self, *, since: datetime, now: datetime, last_reminder: datetime | None = None) -> str | None:
        if not self.enabled or not self.calendar.is_open(now):
            return None
        age = self.calendar.minutes_between(since, now)
        if age >= self.raw["escalation_business_minutes"]:
            return "escalated"
        if self.calendar.minutes_between(last_reminder or since, now) >= self.raw["reminder_business_minutes"]:
            return "reminder"
        return None

    def render_approval(self, card: Any, *, actionable: bool = True) -> dict[str, Any] | None:
        # The existing canonical Teams adapter owns rendering. Configuration
        # contributes validated facts/labels, never a parallel card builder.
        from .universal_interaction.teams import render_configured_approval
        return render_configured_approval(self, card, actionable=actionable)


@dataclass(frozen=True)
class TeamsWorkflowConfigurationFile:
    path: Path

    def load(self) -> TeamsWorkflowConfiguration:
        # Read at each operation: invalid replacement fails closed, never a
        # silent fallback to stale cached policy. Atomic replacement is required.
        content = self.path.read_bytes()
        if len(content) > 131072:
            raise TeamsConfigurationError("workflow configuration exceeds size bound")
        return TeamsWorkflowConfiguration.parse(json.loads(content))
