"""Isolated, fail-closed Grafana-to-Jason SharePoint site access HTTP boundary.

Grafana's server-side datasource proxy must inject a secret service credential
and an authenticated Grafana username. The endpoint never trusts user-selected
principal IDs, Graph roles, tenant IDs, or service identities in request bodies.
Production activation requires independently validated owner allowlist and TLS/
network isolation; never expose this service on the public Internet.
"""
from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler
from typing import Callable

from .site_access_admin import GovernedSiteAccessAdministration


def make_handler(*, administration: GovernedSiteAccessAdministration,
                 service_token: str, allowed_grafana_owners: frozenset[str],
                 approval_verifier: Callable[[str, str, bool], bool]):
    if not service_token or len(service_token) < 32 or not allowed_grafana_owners:
        raise ValueError("Exact Grafana control identity must be provisioned")
    if approval_verifier is None:
        raise ValueError("SharePoint site approval verifier required")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never print sensitive headers or caller payload.

        def _write(self, code: int, payload: dict):
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _authenticated_actor(self) -> str:
            value = str(self.headers.get("Authorization") or "")
            if not value.lower().startswith("bearer "):
                raise PermissionError("SharePoint service authentication required")
            if not hmac.compare_digest(value[7:], service_token):
                raise PermissionError("SharePoint service credential denied")
            actor = str(self.headers.get("X-Grafana-User") or "").strip().casefold()
            if not actor or actor not in allowed_grafana_owners:
                raise PermissionError("Authenticated Grafana Owner identity required")
            return actor

        def do_GET(self):
            try:
                self._authenticated_actor()
                if self.path == "/sharepoint-control/sites":
                    self._write(200, {
                        "status": "ok",
                        "sites": administration.list_sites(),
                        "last_discovery": administration.registry.last_discovery(),
                    })
                elif self.path == "/healthz":
                    self._write(200, {"status": "ok"})
                else:
                    self._write(404, {"error": "not_found"})
            except PermissionError:
                self._write(403, {"error": "access_denied"})
            except Exception:
                self._write(503, {"error": "sharepoint_control_unavailable"})

        def do_POST(self):
            if self.path != "/sharepoint-control/site-access":
                return self._write(404, {"error": "not_found"})
            try:
                actor = self._authenticated_actor()
                length = int(self.headers.get("Content-Length") or "0")
                if not 1 <= length <= 4096:
                    raise ValueError("Invalid request length")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {
                    "site_id", "enabled", "expected_revision", "reason"
                }:
                    raise ValueError("Exact site selection required")
                site_id = body["site_id"]
                enabled = body["enabled"]
                reason = body["reason"]
                if (not isinstance(site_id, str) or not site_id.strip()
                        or type(enabled) is not bool
                        or type(body["expected_revision"]) is not int
                        or not isinstance(reason, str) or not reason.strip()):
                    raise ValueError("Invalid site decision")
                if not approval_verifier(actor, site_id, enabled):
                    raise PermissionError("Site decision lacks exact authorized approval")
                result = administration.change_site_access(
                    authenticated_principal=actor, site_id=site_id, enabled=enabled,
                    approval_reference=reason[:256],
                    expected_revision=body["expected_revision"],
                )
                self._write(200, {"status": "verified", "site": result})
            except PermissionError:
                self._write(403, {"error": "access_denied"})
            except (ValueError, LookupError):
                self._write(409, {"error": "invalid_or_stale_site_access_request"})
            except Exception:
                self._write(503, {"error": "sharepoint_control_unavailable"})

    return Handler
