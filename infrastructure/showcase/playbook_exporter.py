#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(os.environ.get("JASON_REPO_ROOT", Path(__file__).resolve().parents[2]))
SOURCE_REGISTRY = (
    REPO_ROOT
    / "implementation"
    / "autonomous_remediation"
    / "playbook_registry.json"
)
REGISTRY_PATH = Path(
    os.environ.get("JASON_PLAYBOOK_REGISTRY_PATH", "/var/lib/jason/playbooks/registry.json")
)
EVENTS_PATH = Path(
    os.environ.get("JASON_PLAYBOOK_EVENTS_PATH", "/var/lib/jason/playbooks/events.jsonl")
)
HOST = os.environ.get("JASON_PLAYBOOK_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_PLAYBOOK_EXPORTER_PORT", "9468"))
DURATION_BUCKETS = (60, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400)


def _escape(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def _load_registry(path: Path | None = None) -> dict:
    selected = path or REGISTRY_PATH
    if not selected.exists():
        selected = SOURCE_REGISTRY
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"playbooks": []}
    return payload if isinstance(payload, dict) else {"playbooks": []}


def _load_events(path: Path | None = None) -> list[dict]:
    selected = path or EVENTS_PATH
    if not selected.exists():
        return []
    events: list[dict] = []
    try:
        lines = selected.read_text(encoding="utf-8").splitlines()
    except OSError:
        return events
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(item, dict) and str(item.get("playbook_id", "")).strip():
            events.append(item)
    return events


def _timestamp(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _metric_counter(
    lines: list[str],
    metric: str,
    help_text: str,
    counts: Counter[tuple[str, ...]],
    label_names: tuple[str, ...],
) -> None:
    lines.extend([f"# HELP {metric} {help_text}", f"# TYPE {metric} counter"])
    for labels, count in sorted(counts.items()):
        label_text = ",".join(
            f'{name}="{_escape(value)}"'
            for name, value in zip(label_names, labels)
        )
        lines.append(f"{metric}{{{label_text}}} {count}")


def render_metrics(
    *,
    registry_path: Path | None = None,
    events_path: Path | None = None,
) -> str:
    registry = _load_registry(registry_path)
    events = _load_events(events_path)
    playbooks = [
        item for item in registry.get("playbooks", []) if isinstance(item, dict)
    ]

    lines = [
        "# HELP jason_playbook_info Registered Jason playbook metadata.",
        "# TYPE jason_playbook_info gauge",
        "# HELP jason_playbook_enabled Whether the registered playbook is enabled for runtime use.",
        "# TYPE jason_playbook_enabled gauge",
    ]
    for item in playbooks:
        playbook_id = str(item.get("id", "unknown"))
        labels = {
            "playbook_id": playbook_id,
            "name": str(item.get("name", "")),
            "version": str(item.get("version", "")),
            "lifecycle": str(item.get("lifecycle", "unknown")),
            "review_status": str(item.get("review_status", "unknown")),
        }
        label_text = ",".join(
            f'{key}="{_escape(value)}"' for key, value in labels.items()
        )
        lines.append(f"jason_playbook_info{{{label_text}}} 1")
        lines.append(
            f'jason_playbook_enabled{{playbook_id="{_escape(playbook_id)}"}} '
            f'{1 if item.get("enabled") is True else 0}'
        )

    outcomes: Counter[tuple[str, ...]] = Counter()
    classifications: Counter[tuple[str, ...]] = Counter()
    dispositions: Counter[tuple[str, ...]] = Counter()
    compromise_signals: Counter[tuple[str, ...]] = Counter()
    verification: Counter[tuple[str, ...]] = Counter()
    evidence_sources: Counter[tuple[str, ...]] = Counter()
    step_results: Counter[tuple[str, ...]] = Counter()
    reopened: Counter[tuple[str, ...]] = Counter()
    attempts_sum: defaultdict[str, float] = defaultdict(float)
    attempts_count: Counter[str] = Counter()
    duration_sum: defaultdict[str, float] = defaultdict(float)
    duration_count: Counter[str] = Counter()
    duration_buckets: defaultdict[str, Counter[float]] = defaultdict(Counter)
    last_run: dict[str, float] = {}

    for event in events:
        pid = str(event.get("playbook_id", "")).strip()
        if not pid:
            continue
        outcome = str(event.get("outcome", "unknown"))
        outcomes[(pid, outcome)] += 1
        classifications[(pid, str(event.get("classification", "unknown")))] += 1
        dispositions[(pid, str(event.get("security_disposition", "not_applicable")))] += 1
        compromise_signals[(pid, str(event.get("compromise_signal", "not_established")))] += 1
        verification[(pid, "pass" if event.get("verification_passed") is True else "fail")] += 1
        if event.get("reopened") is True:
            reopened[(pid,)] += 1
        for source in event.get("evidence_sources", []) or []:
            evidence_sources[(pid, str(source))] += 1
        for step in event.get("steps", []) or []:
            if isinstance(step, dict):
                step_results[
                    (
                        pid,
                        str(step.get("name", "unknown")),
                        str(step.get("result", "unknown")),
                    )
                ] += 1

        attempts = event.get("attempt_count")
        if isinstance(attempts, (int, float)) and not isinstance(attempts, bool):
            attempts_sum[pid] += float(attempts)
            attempts_count[pid] += 1

        duration = event.get("duration_seconds")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            value = max(0.0, float(duration))
            duration_sum[pid] += value
            duration_count[pid] += 1
            for bucket in DURATION_BUCKETS:
                if value <= bucket:
                    duration_buckets[pid][bucket] += 1

        stamp = _timestamp(event.get("timestamp"))
        if stamp is not None:
            last_run[pid] = max(last_run.get(pid, stamp), stamp)

    _metric_counter(
        lines,
        "jason_playbook_runs_total",
        "Playbook runs by terminal/current outcome.",
        outcomes,
        ("playbook_id", "outcome"),
    )
    _metric_counter(
        lines,
        "jason_playbook_classification_total",
        "Playbook runs by intake classification.",
        classifications,
        ("playbook_id", "classification"),
    )
    _metric_counter(
        lines,
        "jason_playbook_security_disposition_total",
        "Playbook security dispositions without asserting compromise from product health.",
        dispositions,
        ("playbook_id", "disposition"),
    )
    _metric_counter(
        lines,
        "jason_playbook_compromise_signal_total",
        "Explicit compromise-signal classifications recorded by playbook runs.",
        compromise_signals,
        ("playbook_id", "signal"),
    )
    _metric_counter(
        lines,
        "jason_playbook_verification_total",
        "Playbook verification results.",
        verification,
        ("playbook_id", "result"),
    )
    _metric_counter(
        lines,
        "jason_playbook_evidence_source_total",
        "Evidence source use by playbook.",
        evidence_sources,
        ("playbook_id", "source"),
    )
    _metric_counter(
        lines,
        "jason_playbook_step_total",
        "Playbook step outcomes.",
        step_results,
        ("playbook_id", "step", "result"),
    )
    _metric_counter(
        lines,
        "jason_playbook_reopened_total",
        "Tickets/cases reopened after a playbook resolution.",
        reopened,
        ("playbook_id",),
    )

    lines.extend([
        "# HELP jason_playbook_attempts_sum Sum of remediation/diagnostic attempts across playbook runs.",
        "# TYPE jason_playbook_attempts_sum counter",
        "# HELP jason_playbook_attempts_count Number of playbook runs contributing attempt counts.",
        "# TYPE jason_playbook_attempts_count counter",
    ])
    for pid in sorted(set(attempts_sum) | set(attempts_count)):
        label = f'playbook_id="{_escape(pid)}"'
        lines.append(f"jason_playbook_attempts_sum{{{label}}} {attempts_sum[pid]:.6f}")
        lines.append(f"jason_playbook_attempts_count{{{label}}} {attempts_count[pid]}")

    lines.extend([
        "# HELP jason_playbook_run_duration_seconds Playbook run duration histogram.",
        "# TYPE jason_playbook_run_duration_seconds histogram",
    ])
    for pid in sorted(set(duration_sum) | set(duration_count)):
        running = 0
        for bucket in DURATION_BUCKETS:
            running = duration_buckets[pid][bucket]
            lines.append(
                'jason_playbook_run_duration_seconds_bucket'
                f'{{playbook_id="{_escape(pid)}",le="{bucket}"}} {running}'
            )
        lines.append(
            'jason_playbook_run_duration_seconds_bucket'
            f'{{playbook_id="{_escape(pid)}",le="+Inf"}} {duration_count[pid]}'
        )
        lines.append(
            f'jason_playbook_run_duration_seconds_sum{{playbook_id="{_escape(pid)}"}} '
            f'{duration_sum[pid]:.6f}'
        )
        lines.append(
            f'jason_playbook_run_duration_seconds_count{{playbook_id="{_escape(pid)}"}} '
            f'{duration_count[pid]}'
        )

    lines.extend([
        "# HELP jason_playbook_last_run_timestamp_seconds Timestamp of the most recent recorded playbook run.",
        "# TYPE jason_playbook_last_run_timestamp_seconds gauge",
    ])
    for pid, stamp in sorted(last_run.items()):
        lines.append(
            f'jason_playbook_last_run_timestamp_seconds{{playbook_id="{_escape(pid)}"}} {stamp:.3f}'
        )

    lines.extend([
        "# HELP jason_playbook_exporter_build_info Jason playbook exporter metadata.",
        "# TYPE jason_playbook_exporter_build_info gauge",
        'jason_playbook_exporter_build_info{version="1"} 1',
    ])
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/metrics"):
            self.send_response(404)
            self.end_headers()
            return
        payload = render_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Jason playbook exporter listening on {HOST}:{PORT}", flush=True)
    while True:
        server.handle_request()
        time.sleep(0)
