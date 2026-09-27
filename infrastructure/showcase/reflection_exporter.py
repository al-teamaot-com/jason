#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB = Path(os.environ.get("JASON_REFLECTION_DB", "/var/lib/jason/openclaw/reflection.sqlite3"))
HOST = os.environ.get("JASON_REFLECTION_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_REFLECTION_EXPORTER_PORT", "9476"))
_STATES = ("observed", "proposed", "tested", "approved", "promoted", "rejected")


def metrics() -> str:
    available = records = corrections = candidates = regression_pass = regression_fail = 0
    states = {state: 0 for state in _STATES}
    signals: dict[str, int] = {}
    if DB.exists():
        try:
            c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            records = int(c.execute("select count(*) from reflection_records").fetchone()[0])
            corrections = int(c.execute("select count(*) from reflection_user_corrections").fetchone()[0])
            candidates = int(c.execute("select count(*) from improvement_candidates").fetchone()[0])
            for kind, count in c.execute("select signal_kind,count(*) from improvement_candidates group by signal_kind").fetchall():
                signals[str(kind)] = int(count)
            for state, count in c.execute(
                """
                select e.state,count(*) from improvement_candidate_events e
                join (select candidate_key,max(sequence_id) as max_seq from improvement_candidate_events group by candidate_key) latest
                  on latest.candidate_key=e.candidate_key and latest.max_seq=e.sequence_id
                group by e.state
                """
            ).fetchall():
                states[str(state)] = int(count)
            regression_pass = int(c.execute("select count(*) from improvement_regression_evidence where passed=1").fetchone()[0])
            regression_fail = int(c.execute("select count(*) from improvement_regression_evidence where passed=0").fetchone()[0])
            available = 1
            c.close()
        except sqlite3.Error:
            pass
    lines = [
        "# HELP jason_reflection_available Governed Reflection SQLite store readable.",
        "# TYPE jason_reflection_available gauge",
        f"jason_reflection_available {available}",
        "# HELP jason_reflection_records Total bounded reflection records.",
        "# TYPE jason_reflection_records gauge",
        f"jason_reflection_records {records}",
        "# HELP jason_reflection_corrections Authenticated user-correction signals.",
        "# TYPE jason_reflection_corrections gauge",
        f"jason_reflection_corrections {corrections}",
        "# HELP jason_reflection_candidates Improvement candidates by current lifecycle state.",
        "# TYPE jason_reflection_candidates gauge",
        f'jason_reflection_candidates{{state="all"}} {candidates}',
    ]
    lines.extend(f'jason_reflection_candidates{{state="{state}"}} {states.get(state,0)}' for state in _STATES)
    lines.extend([
        "# HELP jason_reflection_regressions Durable CI regression evidence by outcome.",
        "# TYPE jason_reflection_regressions gauge",
        f'jason_reflection_regressions{{result="passed"}} {regression_pass}',
        f'jason_reflection_regressions{{result="failed"}} {regression_fail}',
        "# HELP jason_reflection_signals Improvement candidates by bounded signal kind.",
        "# TYPE jason_reflection_signals gauge",
    ])
    lines.extend(f'jason_reflection_signals{{kind="{kind}"}} {count}' for kind, count in sorted(signals.items()))
    lines.append("")
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/metrics"}:
            self.send_response(404); self.end_headers(); return
        body = metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer((HOST, PORT), Handler).serve_forever()
