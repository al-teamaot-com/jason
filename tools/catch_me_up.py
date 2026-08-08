#!/usr/bin/env python3
"""Generate a secret-safe Project Jason session handoff snapshot."""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, platform, re, shutil, socket, subprocess, sys

SECRET_PATTERNS=(re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key|unseal|credential)\s*[:=]\s*\S+"),re.compile(r"(?i)hvs\.[A-Za-z0-9_-]+"),re.compile(r"(?i)s\.[A-Za-z0-9_-]{10,}"))
CANONICAL_DOCS=("README.md","TODO.md","07-Roadmap/Jason-Roadmap.md","07-Roadmap/Jason-Roadmap-Status.json","07-Operations/Jason-Secret-Provider-Deployment-Record.md","07-Operations/Jason-OpenBao-Initialization-and-Recovery-Record.md","10-Milestones/M-001-Kernel-Foundation.md","10-Milestones/M-002-Release-and-Recovery-Pipeline.md","10-Milestones/M-003-Release-Governance-Hardening.md")
RELEVANT_SYSTEMD_UNITS=("jason-openbao-backup.service","jason-openbao-backup.timer","jason-status-exporter.service","docker.service")

def sanitize(text):
    clean=text.replace("\x00","")
    for pattern in SECRET_PATTERNS:
        clean=pattern.sub(lambda m:m.group(0).split(":",1)[0].split("=",1)[0]+": [REDACTED]",clean)
    return clean

def run(cmd,cwd=None,timeout=12):
    try:
        p=subprocess.run(cmd,cwd=str(cwd) if cwd else None,capture_output=True,text=True,timeout=timeout,check=False)
        return p.returncode,sanitize(((p.stdout or "")+(p.stderr or "")).strip())
    except (OSError,subprocess.SubprocessError) as exc:return 127,sanitize(f"unavailable: {exc}")

def find_repo_root(start):
    current=start.resolve()
    for candidate in (current,*current.parents):
        if (candidate/".git").exists() and (candidate/"README.md").exists():return candidate
    code,out=run(["git","rev-parse","--show-toplevel"],cwd=current)
    if code==0 and out:return pathlib.Path(out.splitlines()[0]).resolve()
    raise SystemExit("ERROR: Could not locate the Jason git repository.")

def heading(lines,title):lines.extend(["",f"## {title}",""])
def bullet(lines,label,value):lines.append(f"- **{label}:** {sanitize(str(value))}")
def codeblock(lines,content,language="text"):lines.extend([f"```{language}",*sanitize(content).splitlines() or ["(none)"],"```"])
def read_small(path,limit=12000):
    try:return sanitize(path.read_text(encoding="utf-8",errors="replace")[:limit])
    except OSError as exc:return f"unavailable: {exc}"
def extract_status_lines(text):
    wanted=[]
    for raw in text.splitlines():
        line=raw.strip(); low=line.lower()
        if line and any(k in low for k in ("blocked","unverified","remaining","next","current","status","complete","ready","gate")):wanted.append(sanitize(line))
        if len(wanted)>=24:break
    return wanted

def collect_git(repo,lines):
    heading(lines,"Repository State")
    for label,cmd in (("Branch",["git","branch","--show-current"]),("HEAD",["git","rev-parse","HEAD"]),("Remote",["git","remote","get-url","origin"])):
        _,out=run(cmd,cwd=repo); bullet(lines,label,out or "unknown")
    _,status=run(["git","status","--short"],cwd=repo); lines.append("\n### Working tree"); codeblock(lines,status or "clean")
    _,commits=run(["git","log","-8","--date=iso","--pretty=format:%h | %ad | %s"],cwd=repo); lines.append("\n### Recent commits"); codeblock(lines,commits)

def collect_host(lines):
    heading(lines,"Jason Host"); bullet(lines,"Generated",dt.datetime.now().astimezone().isoformat(timespec="seconds")); bullet(lines,"Hostname",socket.gethostname()); bullet(lines,"User",os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"); bullet(lines,"OS",platform.platform()); bullet(lines,"Python",platform.python_version()); bullet(lines,"Kernel",platform.release()); _,ips=run(["hostname","-I"]); bullet(lines,"Host IPs",ips or "unknown")

def protected_artifact_metadata(path):
    """Return existence/metadata without reading contents; permission denial is a valid protected state."""
    try:
        st=os.stat(path)
        return f"yes; mode {oct(st.st_mode & 0o777)}; size {st.st_size} bytes (contents NOT read)"
    except PermissionError:
        return "present or protected; metadata inaccessible to current user (contents NOT read)"
    except FileNotFoundError:
        return "no"
    except OSError as exc:
        return f"unknown; metadata check unavailable: {sanitize(str(exc))}"

def collect_runtime(repo,lines):
    heading(lines,"Runtime / Infrastructure")
    if shutil.which("docker"):
        _,docker=run(["docker","ps","--format","{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}"],cwd=repo); lines.append("### Docker containers"); codeblock(lines,docker or "No running containers")
    else:lines.append("- Docker CLI: unavailable")
    if shutil.which("systemctl"):
        lines.append("\n### Relevant systemd units")
        for unit in RELEVANT_SYSTEMD_UNITS:
            code,state=run(["systemctl","is-active",unit]); status=state.splitlines()[0] if state else ("inactive/unknown" if code else "active"); lines.append(f"- `{unit}`: {status}")
    if shutil.which("curl"):
        _,health=run(["curl","-sS","--max-time","3","http://127.0.0.1:8200/v1/sys/health"])
        if health:
            try:
                obj=json.loads(health); safe={k:obj.get(k) for k in ("initialized","sealed","standby","performance_standby","replication_performance_mode","replication_dr_mode","server_time_utc","version","cluster_name","cluster_id") if k in obj}; lines.append("\n### OpenBao health (no authentication)"); codeblock(lines,json.dumps(safe,indent=2,sort_keys=True),"json")
            except json.JSONDecodeError:lines.append("\n### OpenBao health"); codeblock(lines,health[:1500])
    for path in ("/etc/jason/openbao.token","/opt/jason/bootstrap/secrets/openbao/init.json"):
        bullet(lines,f"Protected artifact `{path}`",protected_artifact_metadata(path))

def collect_project_docs(repo,lines):
    heading(lines,"Canonical Project Signals")
    for rel in CANONICAL_DOCS:
        path=repo/rel
        try:st=path.stat()
        except FileNotFoundError:lines.append(f"### `{rel}`\n- Missing"); continue
        except OSError as exc:lines.append(f"### `{rel}`\n- Metadata unavailable: {sanitize(str(exc))}"); continue
        lines.append(f"### `{rel}`"); bullet(lines,"Modified",dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds")); signals=extract_status_lines(read_small(path)); lines.extend([f"- {s}" for s in signals] if signals else ["- No concise status/gate lines detected."])

def collect_session_records(repo,lines):
    heading(lines,"Session Records"); session_dir=repo/"08-Session-Records"
    if not session_dir.exists():lines.append("- Session record directory missing."); return
    try:records=sorted((p for p in session_dir.glob("*.md") if p.name.lower()!="readme.md"),key=lambda p:p.stat().st_mtime,reverse=True)[:5]
    except OSError as exc:lines.append(f"- Session records unavailable: {sanitize(str(exc))}"); return
    if not records:lines.append("- No dated session records found."); return
    for p in records:
        try:bullet(lines,p.name,dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="seconds"))
        except OSError:pass

def collect_recent_evidence(lines):
    heading(lines,"Recent Non-Secret Evidence"); items=[]
    for root in (pathlib.Path.home()/"Jason-Evidence",pathlib.Path("/var/lib/jason/evidence")):
        try:
            if root.exists():items.extend(p for p in root.rglob("*") if p.is_file())
        except OSError:pass
    def safe_mtime(p):
        try:return p.stat().st_mtime
        except OSError:return 0
    items.sort(key=safe_mtime,reverse=True)
    for p in items[:20]:
        try:lines.append(f"- `{p}` — {dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec='seconds')} — {p.stat().st_size} bytes")
        except OSError:continue
    if not items:lines.append("- No evidence files found in standard evidence locations.")

def collect_recovery_clues(lines):
    heading(lines,"Recovery / OpenClaw Clues"); lines.append("Checks report names, states, paths, and metadata only; protected values are never read.")
    for root in (pathlib.Path("/etc/openclaw"),pathlib.Path.home()/".openclaw",pathlib.Path("/opt/openclaw"),pathlib.Path("/opt/jason")):
        try:exists=root.exists()
        except OSError:exists=False
        if not exists:continue
        lines.append(f"\n### `{root}`")
        try:
            matches=[]
            for p in root.rglob("*"):
                if any(term in p.name.lower() for term in ("recovery","backup","generate-root","openclaw")):matches.append(p)
                if len(matches)>=30:break
            for p in matches:
                try:lines.append(f"- {'dir' if p.is_dir() else 'file'}: `{p}`")
                except OSError:continue
            if not matches:lines.append("- No filename-level recovery/generate-root clues found.")
        except OSError as exc:lines.append(f"- Scan unavailable: {sanitize(str(exc))}")

def build_snapshot(repo):
    lines=["# Project Jason — CatchMeUp","","> Paste this entire snapshot into a new ChatGPT session and say: **Continue Project Jason from this CatchMeUp snapshot.**","> This report is intentionally secret-safe. It contains no credential values, OpenBao tokens, unseal shares, passwords, or API keys."]
    collect_host(lines); collect_git(repo,lines); collect_runtime(repo,lines); collect_project_docs(repo,lines); collect_session_records(repo,lines); collect_recent_evidence(lines); collect_recovery_clues(lines)
    heading(lines,"Instructions For The Next Session"); lines.extend(["1. Treat this snapshot plus the Jason GitHub repository as the authoritative starting point.","2. Do **not** restart architectural discovery or re-ask decisions already recorded in canonical Jason documents.","3. Continue in **larger workstreams/batches**, not one-command-at-a-time guidance.","4. Preserve Jason's core rule: agents never communicate directly; all inter-agent coordination goes through the central orchestrator.","5. Preserve identity-first authorization, policy-as-data, capability registry, centralized evidence, event-based auditability, and integrate-before-innovate.","6. Never expose protected values from OpenBao, init artifacts, token files, shell history, or environment variables.","7. Reconcile any contradiction between this host snapshot and repository-controlled canonical records before making destructive or security-sensitive changes."])
    return "\n".join(lines).rstrip()+"\n"

def main():
    parser=argparse.ArgumentParser(description="Generate a Project Jason session handoff snapshot."); parser.add_argument("--output",default=None); parser.add_argument("--stdout-only",action="store_true"); args=parser.parse_args(); repo=find_repo_root(pathlib.Path.cwd()); snapshot=build_snapshot(repo)
    if args.stdout_only:sys.stdout.write(snapshot); return 0
    out=pathlib.Path(args.output).expanduser() if args.output else pathlib.Path.home()/f"Jason-CatchMeUp-{dt.datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}.md"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(snapshot,encoding="utf-8"); print(snapshot); print(f"\nCatchMeUp saved to: {out}",file=sys.stderr); return 0
if __name__=="__main__":raise SystemExit(main())
