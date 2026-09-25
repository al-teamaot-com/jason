from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Reading:
    at: datetime
    level: int


@dataclass(frozen=True)
class ReplacementEvent:
    previous_at: datetime
    replacement_at: datetime
    previous_level: int
    new_level: int
    confidence: str


@dataclass(frozen=True)
class Forecast:
    current_level: int
    burn_pct_per_day: float | None
    days_remaining: float | None
    action: str
    confidence: str
    reason: str


def detect_replacements(readings: Sequence[Reading]) -> list[ReplacementEvent]:
    ordered = sorted(readings, key=lambda r: r.at)
    events: list[ReplacementEvent] = []
    for prev, cur in zip(ordered, ordered[1:]):
        jump = cur.level - prev.level
        if prev.level <= 15 and cur.level >= 90 and jump >= 60:
            confidence = "high" if prev.level <= 10 and cur.level >= 95 else "medium"
            events.append(ReplacementEvent(prev.at, cur.at, prev.level, cur.level, confidence))
    return events


def estimate_burn_pct_per_day(readings: Sequence[Reading], lookback_days: int = 30) -> float | None:
    ordered = sorted(readings, key=lambda r: r.at)
    if len(ordered) < 3:
        return None
    cutoff = ordered[-1].at.timestamp() - lookback_days * 86400
    recent = [r for r in ordered if r.at.timestamp() >= cutoff]
    slopes: list[float] = []
    for prev, cur in zip(recent, recent[1:]):
        elapsed_days = (cur.at - prev.at).total_seconds() / 86400
        if elapsed_days <= 0:
            continue
        delta = prev.level - cur.level
        if 0 < delta <= 25:  # ignore replacements/resets and implausible jumps
            slopes.append(delta / elapsed_days)
    return median(slopes) if slopes else None


def forecast(readings: Sequence[Reading], seasonal_factor: float = 1.0) -> Forecast:
    if not readings:
        return Forecast(0, None, None, "needs_review", "low", "no readings")
    ordered = sorted(readings, key=lambda r: r.at)
    current = ordered[-1].level
    burn = estimate_burn_pct_per_day(ordered)
    if burn is None or burn <= 0:
        action = "ship_today" if current <= 5 else "needs_review" if current <= 15 else "watch"
        return Forecast(current, None, None, action, "low", "insufficient declining history")
    adjusted = burn * max(0.25, min(seasonal_factor, 4.0))
    days = current / adjusted if adjusted else None
    if current <= 5 or (days is not None and days <= 7):
        action = "ship_today"
    elif current <= 15 or (days is not None and days <= 14):
        action = "ship_soon"
    else:
        action = "watch"
    confidence = "high" if len(ordered) >= 8 else "medium" if len(ordered) >= 4 else "low"
    return Forecast(current, adjusted, days, action, confidence, "trend adjusted by customer/device seasonal factor")
