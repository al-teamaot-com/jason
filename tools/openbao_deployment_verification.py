from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Sequence


@dataclass(frozen=True, slots=True)
class ProbeResult:
    name: str
    status: str
    value: str
    source: str


@dataclass(frozen=True, slots=True)
class VerificationReport:
    schema_version: str
    collected_at: str
    host: str
    probes: tuple[ProbeResult, ...]
    overall_status: str


Runner = Callable[..., subprocess.CompletedProcess[str]]

SAFE_COMMANDS = (
    ("systemctl", "show", "jason-openbao-backup.service", "--property=LoadState,ActiveState,FragmentPath,ExecStart", "--no-pager"),
    ("systemctl", "show", "jason-openbao-backup.timer", "--property=LoadState,ActiveState,FragmentPath,NextElapseUSecRealtime", "--no-pager"),
    ("systemctl", "show", "openbao.service", "--property=LoadState,ActiveState,FragmentPath,ExecStart", "--no-pager"),
    ("systemctl", "show", "vault.service", "--property=LoadState,ActiveState,FragmentPath,ExecStart", "--no-pager"),
    ("docker", "ps", "--all", "--filter", "name=^/openbao$", "--format", "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"),
    ("docker", "inspect", "openbao", "--format", "name={{.Name}} image={{.Config.Image}} status={{.State.Status}} mounts={{range .Mounts}}{{.Type}}:{{.Source}}->{{.Destination}};{{end}}"),
    ("podman", "ps", "--all", "--filter", "name=^openbao$", "--format", "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"),
)

SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(?:^|\s)(?:root[_ -]?token|unseal[_ -]?key|recovery[_ -]?key|password|client[_ -]?secret|secret)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(?:^|\s)(?:token)\s*[=:]\s*\S+"),
)


def _redact(text: str) -> str:
    safe_lines: list[str] = []
    for raw_line in text.splitlines():
        if any(pattern.search(raw_line) for pattern in SENSITIVE_PATTERNS):
            safe_lines.append("[REDACTED SENSITIVE LINE]")
        else:
            safe_lines.append(raw_line[:1000])
    return "\n".join(safe_lines).strip()


def _run(command: Sequence[str], *, runner: Runner, timeout_seconds: float) -> ProbeResult:
    executable = shutil.which(command[0])
    if executable is None:
        return ProbeResult(command[0], "not_available", "", "PATH")
    try:
        result = runner(
            [executable, *command[1:]],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(" ".join(command), "timeout", "", executable)
    except OSError:
        return ProbeResult(" ".join(command), "error", "", executable)

    value = _redact(result.stdout or result.stderr)
    status = "ok" if result.returncode == 0 else f"exit_{result.returncode}"
    return ProbeResult(" ".join(command), status, value, executable)


def _file_probe(path: Path) -> ProbeResult:
    if not path.exists():
        return ProbeResult(str(path), "not_found", "", str(path))
    if not path.is_file():
        return ProbeResult(str(path), "not_file", "", str(path))
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return ProbeResult(
        str(path),
        "ok",
        f"size_bytes={len(data)} sha256={digest}",
        str(path),
    )


def collect_report(*, runner: Runner = subprocess.run, timeout_seconds: float = 5.0) -> VerificationReport:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    probes = [
        _run(command, runner=runner, timeout_seconds=timeout_seconds)
        for command in SAFE_COMMANDS
    ]
    probes.extend(
        _file_probe(path)
        for path in (
            Path("/etc/systemd/system/jason-openbao-backup.service"),
            Path("/etc/systemd/system/jason-openbao-backup.timer"),
            Path("/etc/systemd/system/openbao.service"),
            Path("/etc/openbao/openbao.hcl"),
            Path("/usr/local/bin/jason-secret"),
        )
    )

    hostname_command = shutil.which("hostname")
    host = "unknown"
    if hostname_command:
        try:
            host = runner(
                [hostname_command],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            ).stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            host = "unknown"

    meaningful = [probe for probe in probes if probe.status == "ok" and probe.value]
    overall = "evidence_collected" if meaningful else "insufficient_evidence"
    return VerificationReport(
        schema_version="0.1",
        collected_at=datetime.now(timezone.utc).isoformat(),
        host=host,
        probes=tuple(probes),
        overall_status=overall,
    )


def render_markdown(report: VerificationReport) -> str:
    lines = [
        "# OpenBao Deployment Verification Evidence",
        "",
        f"**Collected at:** {report.collected_at}",
        f"**Host:** {report.host}",
        f"**Overall status:** {report.overall_status}",
        "",
        "This file contains non-secret deployment facts only. It is evidence for updating the canonical deployment record; it is not itself an approval.",
        "",
        "| Probe | Status | Evidence | Source |",
        "|---|---|---|---|",
    ]
    for probe in report.probes:
        value = probe.value.replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| `{probe.name}` | `{probe.status}` | {value or '—'} | `{probe.source}` |")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect non-secret OpenBao deployment evidence with bounded probes."
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    return parser


def _validate_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {resolved}")
    repository = Path.cwd().resolve()
    if resolved == repository or repository in resolved.parents:
        raise PermissionError("Verification evidence must be written outside the repository.")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    json_output = _validate_output(args.json_output)
    markdown_output = _validate_output(args.markdown_output)

    report = collect_report(timeout_seconds=args.timeout_seconds)
    json_output.write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(render_markdown(report), encoding="utf-8")

    print("APPROVED: Non-secret OpenBao deployment evidence collected.")
    print(f"JSON evidence: {json_output}")
    print(f"Markdown evidence: {markdown_output}")
    print("The canonical deployment record remains unchanged pending governed review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
