"""Persistent AOT SharePoint site access switches; never provider permission grants.

This module is intentionally independent of the deployed ticket core. Grafana
must call a separately authenticated, governed server API; it must NEVER edit
this database directly. Call require_site_access on every provider operation.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A nonempty exact identifier is required")
    return value.strip()


class SharePointSiteAccess:
    """Durable fail-closed site switches with auditable, atomic changes."""

    def __init__(self, path: str, *, tenant_id: str, now: Callable[[], str] = _utc):
        self.path = path
        self.tenant_id = _valid(tenant_id)
        self.now = now
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sharepoint_sites (
                    tenant_id TEXT NOT NULL,
                    site_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    web_url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (tenant_id, site_id)
                );
                CREATE TABLE IF NOT EXISTS sharepoint_site_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    site_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event TEXT NOT NULL,
                    old_enabled INTEGER,
                    new_enabled INTEGER,
                    revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sharepoint_discovery_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    sites_seen INTEGER NOT NULL,
                    error TEXT
                );
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def discover(self, sites: Iterable[Mapping[str, str]], *,
                 actor: str = "jason-sharepoint-daily-discovery") -> int:
        """Apply a successful, COMPLETE tenant site enumeration atomically.

        Callers must finish Graph pagination BEFORE invoking this method.
        On a Graph error invoke discovery_failed instead. Never grant by scan.
        """
        actor = _valid(actor)
        unique = {}
        for site in sites:
            if site.get("tenant_id") != self.tenant_id:
                raise PermissionError("Cross-tenant SharePoint site rejected")
            sid = _valid(site.get("site_id"))
            unique[sid] = (_valid(site.get("name")), _valid(site.get("web_url")))
        stamp = self.now()
        with self._connect() as db:
            for sid, (name, url) in unique.items():
                old = db.execute(
                    "SELECT revision FROM sharepoint_sites WHERE tenant_id=? AND site_id=?",
                    (self.tenant_id, sid),
                ).fetchone()
                if old is None:
                    db.execute(
                        """INSERT INTO sharepoint_sites
                           (tenant_id,site_id,name,web_url,enabled,first_seen,last_seen)
                           VALUES(?,?,?,?,0,?,?)""",
                        (self.tenant_id, sid, name, url, stamp, stamp),
                    )
                    db.execute(
                        """INSERT INTO sharepoint_site_audit
                           (at,tenant_id,site_id,actor,event,old_enabled,new_enabled,revision)
                           VALUES(?,?,?,?,?,NULL,0,1)""",
                        (stamp, self.tenant_id, sid, actor, "discovered_disabled"),
                    )
                else:
                    db.execute(
                        """UPDATE sharepoint_sites SET name=?,web_url=?,last_seen=?
                           WHERE tenant_id=? AND site_id=?""",
                        (name, url, stamp, self.tenant_id, sid),
                    )
            db.execute(
                """INSERT INTO sharepoint_discovery_runs
                   (at,tenant_id,success,sites_seen,error) VALUES(?,?,1,?,NULL)""",
                (stamp, self.tenant_id, len(unique)),
            )
        return len(unique)

    def discovery_failed(self, message: str) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO sharepoint_discovery_runs
                   (at,tenant_id,success,sites_seen,error) VALUES(?,?,0,0,?)""",
                (self.now(), self.tenant_id, str(message)[:500]),
            )

    def set_enabled(self, *, site_id: str, enabled: bool, actor: str,
                    approval_reference: str, expected_revision: int) -> int:
        """Only an upstream authenticated Owner/admin authorization may call this.

        The API boundary must validate the actor and approval/reference before
        calling; merely knowing an ID cannot confer authority.
        """
        site_id, actor = _valid(site_id), _valid(actor)
        _valid(approval_reference)
        if type(enabled) is not bool or type(expected_revision) is not int:
            raise ValueError("Expected explicit bool and integer revision")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                """SELECT enabled,revision FROM sharepoint_sites
                   WHERE tenant_id=? AND site_id=?""", (self.tenant_id, site_id)
            ).fetchone()
            if old is None:
                raise LookupError("Site is not discovered; no implicit grants")
            if old["revision"] != expected_revision:
                raise ValueError("Stale site-access revision")
            if bool(old["enabled"]) == enabled:
                return old["revision"]
            revision = old["revision"] + 1
            db.execute(
                """UPDATE sharepoint_sites SET enabled=?,revision=?
                   WHERE tenant_id=? AND site_id=?""",
                (int(enabled), revision, self.tenant_id, site_id),
            )
            db.execute(
                """INSERT INTO sharepoint_site_audit
                   (at,tenant_id,site_id,actor,event,old_enabled,new_enabled,revision)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (self.now(), self.tenant_id, site_id,
                 actor + " [" + approval_reference + "]", "site_access_changed",
                 old["enabled"], int(enabled), revision),
            )
            return revision

    def require_site_access(self, *, tenant_id: str, site_id: str) -> None:
        if tenant_id != self.tenant_id:
            raise PermissionError("SharePoint tenant denied")
        with self._connect() as db:
            row = db.execute(
                """SELECT enabled FROM sharepoint_sites
                   WHERE tenant_id=? AND site_id=?""",
                (self.tenant_id, _valid(site_id)),
            ).fetchone()
        if row is None or row["enabled"] != 1:
            raise PermissionError("SharePoint site disabled or unknown")

    def sites(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT site_id,name,web_url,enabled,first_seen,last_seen,revision
                   FROM sharepoint_sites WHERE tenant_id=? ORDER BY name,site_id""",
                (self.tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def last_discovery(self) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT at,success,sites_seen,error FROM sharepoint_discovery_runs
                   WHERE tenant_id=? ORDER BY id DESC LIMIT 1""",
                (self.tenant_id,),
            ).fetchone()
        return dict(row) if row else None
