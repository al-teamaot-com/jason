"""Provider-neutral, deterministic organization matching. No provider calls or writes.

Consumers must supply records from separately authorized governed reads. A proposed
match is never an approved or durable company mapping.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable
from unicodedata import normalize as unicode_normalize
from urllib.parse import urlsplit
import re


_COMMON_DOMAINS = frozenset({
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "aol.com",
    "icloud.com", "live.com", "msn.com", "proton.me", "protonmail.com",
    "example.com", "example.org", "example.net", "intuit.com",
})
_SUFFIXES = frozenset({"llc", "inc", "incorporated", "corp", "corporation",
                       "ltd", "limited", "co", "company", "pllc"})


def _words(value: str) -> str:
    s = unicode_normalize("NFKC", value or "").casefold()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def _name(value: str) -> str:
    parts = _words(value).split()
    while len(parts) > 1 and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def _phone(value: str) -> str:
    digits = re.sub(r"[^0-9]", "", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or len(set(digits)) == 1:
        return ""
    return digits


def _domain(value: str) -> str:
    v = (value or "").strip().casefold()
    if not v:
        return ""
    if "@" in v and "://" not in v:
        v = v.rsplit("@", 1)[-1]
    elif "://" not in v:
        v = "https://" + v
    try:
        host = (urlsplit(v).hostname or "").removeprefix("www.").rstrip(".")
    except ValueError:
        return ""
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host):
        return ""
    if host in _COMMON_DOMAINS or host.endswith((".example.com", ".example.net", ".example.org")):
        return ""
    return host


def _email(value: str) -> str:
    v = (value or "").strip().casefold()
    return v if v.count("@") == 1 and len(v) <= 254 else ""


def _postal(value: str) -> str:
    match = re.match(r"\s*([0-9]{5})(?:-[0-9]{4})?\s*$", value or "")
    return match.group(1) if match else ""


@dataclass(frozen=True, slots=True)
class OrganizationRecord:
    source: str
    source_id: str
    scope_id: str
    name: str
    legal_name: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    street: str = ""
    postal_code: str = ""

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.source, self.source_id, self.scope_id, self.name)):
            raise ValueError("source, durable source ID, scope, and name required")
        if any(len(v) > 512 for v in (self.source, self.source_id, self.scope_id, self.name)):
            raise ValueError("Organization identifier/name exceeds bound")


@dataclass(frozen=True, slots=True)
class VerifiedOrganizationLink:
    """Evidence must originate from a separately governed approval registry."""

    left_id: str
    right_id: str
    approval_id: str


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    right_id: str
    score: int
    signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchResult:
    left_id: str
    status: str  # verified, probable, possible, ambiguous, unmatched
    candidates: tuple[MatchCandidate, ...]
    reason: str


def _score(a: OrganizationRecord, b: OrganizationRecord) -> MatchCandidate:
    signals: list[str] = []
    score = 0
    names_a = {_name(a.name), _name(a.legal_name)} - {""}
    names_b = {_name(b.name), _name(b.legal_name)} - {""}
    if names_a & names_b:
        score += 55
        signals.append("name_exact")
    elif names_a and names_b:
        similarity = max(SequenceMatcher(None, x, y).ratio()
                         for x in names_a for y in names_b if len(x) >= 8 and len(y) >= 8) if (
                             any(len(x) >= 8 for x in names_a)
                             and any(len(y) >= 8 for y in names_b)) else 0.0
        if similarity >= 0.88:
            score += 30
            signals.append("name_similar")

    if _phone(a.phone) and _phone(a.phone) == _phone(b.phone):
        score += 25
        signals.append("phone_exact")
    corporate_email_match = bool(
        _email(a.email) and _email(a.email) == _email(b.email)
        and _domain(a.email) and _domain(b.email)
    )
    if corporate_email_match:
        score += 25
        signals.append("email_exact")
    # A matching email address and its domain form one evidence channel.
    domains_a = {_domain(a.website), _domain(a.email)} - {""}
    domains_b = {_domain(b.website), _domain(b.email)} - {""}
    if domains_a & domains_b and not corporate_email_match:
        score += 20
        signals.append("business_domain_exact")
    if (_words(a.street) and _words(a.street) == _words(b.street)
            and _postal(a.postal_code) and _postal(a.postal_code) == _postal(b.postal_code)):
        score += 35
        signals.append("street_postal_exact")
    return MatchCandidate(right_id=b.source_id, score=min(score, 100),
                          signals=tuple(signals))


def match_organizations(
    left: Iterable[OrganizationRecord],
    right: Iterable[OrganizationRecord],
    *,
    scope_id: str,
    left_source: str,
    right_source: str,
    verified_links: Iterable[VerifiedOrganizationLink] = (),
    max_records: int = 2000,
) -> tuple[MatchResult, ...]:
    """Return proposals for exactly one caller-approved scope and source pair.

    Only links supplied by a separate trusted approval registry can be 'verified'.
    This function NEVER approves links, writes durable mappings, or fetches data.
    """
    if not all(isinstance(v, str) and v.strip() for v in
               (scope_id, left_source, right_source)):
        raise ValueError("Exact approved scope and providers required")
    if left_source == right_source:
        raise ValueError("Matching two identical source systems is not allowed")
    lhs, rhs, links = tuple(left), tuple(right), tuple(verified_links)
    if len(lhs) > max_records or len(rhs) > max_records or len(links) > max_records:
        raise ValueError("Bounded record limit exceeded")
    if any(v.scope_id != scope_id or v.source != left_source for v in lhs):
        raise PermissionError("Left source/scope mismatch")
    if any(v.scope_id != scope_id or v.source != right_source for v in rhs):
        raise PermissionError("Right source/scope mismatch")
    left_ids = [x.source_id for x in lhs]
    right_ids = [x.source_id for x in rhs]
    if len(set(left_ids)) != len(left_ids) or len(set(right_ids)) != len(right_ids):
        raise ValueError("Duplicate provider record IDs")
    li, ri = set(left_ids), set(right_ids)
    verified: dict[str, str] = {}
    used_right: set[str] = set()
    for link in links:
        if not isinstance(link, VerifiedOrganizationLink) or not link.approval_id.strip():
            raise ValueError("Only evidence-backed approved links are accepted")
        if (link.left_id not in li or link.right_id not in ri
                or link.left_id in verified or link.right_id in used_right):
            raise ValueError("Verified link is missing, out of scope, or conflicts")
        verified[link.left_id] = link.right_id
        used_right.add(link.right_id)

    proposed: dict[str, list[MatchCandidate]] = {}
    for item in lhs:
        if item.source_id in verified:
            continue
        candidates = [_score(item, other) for other in rhs if other.source_id not in used_right]
        proposed[item.source_id] = sorted(
            [c for c in candidates if c.score >= 55 or "name_similar" in c.signals],
            key=lambda c: (-c.score, c.right_id),
        )
    owners: dict[str, list[str]] = {}
    for left_id, candidates in proposed.items():
        if candidates:
            owners.setdefault(candidates[0].right_id, []).append(left_id)

    results: list[MatchResult] = []
    for item in lhs:
        key = item.source_id
        if key in verified:
            results.append(MatchResult(key, "verified",
                                       (MatchCandidate(verified[key], 100, ("approved_mapping",)),),
                                       "Verified by independent governance approval evidence"))
            continue
        candidates = proposed[key]
        if not candidates:
            results.append(MatchResult(key, "unmatched", (), "No candidate met evidence threshold"))
            continue
        best = candidates[0]
        runner = candidates[1] if len(candidates) > 1 else None
        if len(owners.get(best.right_id, [])) > 1:
            status, why = "ambiguous", "Multiple source records claim the same target"
        elif runner is not None and runner.score >= best.score - 20:
            status, why = "ambiguous", "Multiple target candidates have competing evidence"
        elif best.score >= 75 and "name_exact" in best.signals and len(best.signals) >= 2:
            status, why = "probable", "Strong unique evidence; not an approved ID mapping"
        else:
            status, why = "possible", "Insufficient independent evidence for probable match"
        results.append(MatchResult(key, status, tuple(candidates[:5]), why))
    return tuple(results)
