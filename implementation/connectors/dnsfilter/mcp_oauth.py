from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from connectors.core.contracts import ConnectorConfigurationError, ConnectorTransportError

DNSFILTER_MCP_URL = "https://mcp.dnsfilter.com/mcp"
DNSFILTER_MCP_RESOURCE = "https://mcp.dnsfilter.com/"
DNSFILTER_PROTECTED_RESOURCE_METADATA = (
    "https://mcp.dnsfilter.com/.well-known/oauth-protected-resource"
)
DNSFILTER_AUTHORIZATION_SERVER_METADATA = (
    "https://mcp.dnsfilter.com/.well-known/oauth-authorization-server"
)
DNSFILTER_MCP_OAUTH_DB_DEFAULT = Path(
    "/var/lib/jason/openclaw/dnsfilter-mcp/oauth.sqlite3"
)
DNSFILTER_MCP_REDIRECT_URI_DEFAULT = (
    "https://mcp-jason.teamaot.com/oauth/dnsfilter/callback"
)
DNSFILTER_OAUTH_SCOPE = "openid profile email offline_access"
_USER_AGENT = "Mozilla/5.0 Project-Jason-DNSFilter-MCP/1.0"


class DnsFilterMcpOAuthError(RuntimeError):
    """Safe OAuth failure that must never echo credentials or tokens."""


@dataclass(frozen=True, slots=True)
class DnsFilterOAuthStatus:
    registered: bool
    connected: bool
    expires_at: int | None
    has_refresh_token: bool
    pending_authorization: bool


class DnsFilterMcpOAuthStore:
    """Durable local OAuth state shared by Jason runtime and MCP edge.

    The database lives on Jason's existing protected /var/lib/jason/openclaw
    volume. It stores OAuth client registration, tokens, and short-lived PKCE
    transactions. No token values are exposed by the status methods.
    """

    def __init__(self, path: Path = DNSFILTER_MCP_OAUTH_DB_DEFAULT) -> None:
        self.path = Path(path)
        self._initialized = False

    def _raw_connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        self._ensure_initialized()
        return self._raw_connect()

    def _initialize(self) -> None:
        with self._raw_connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_registration (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    payload_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_token (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    payload_json TEXT NOT NULL,
                    expires_at INTEGER,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_pending (
                    state TEXT PRIMARY KEY,
                    code_verifier TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "DELETE FROM oauth_pending WHERE expires_at < ?",
                (int(time.time()),),
            )
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def get_registration(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM oauth_registration WHERE singleton = 1"
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def set_registration(self, payload: Mapping[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO oauth_registration(singleton,payload_json,updated_at)
                VALUES(1,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (json.dumps(dict(payload), sort_keys=True), int(time.time())),
            )

    def get_token(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json,expires_at FROM oauth_token WHERE singleton = 1"
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        if row["expires_at"] is not None:
            payload["_expires_at"] = int(row["expires_at"])
        return payload

    def set_token(self, payload: Mapping[str, Any]) -> None:
        token = dict(payload)
        expires_at = _token_expires_at(token)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO oauth_token(singleton,payload_json,expires_at,updated_at)
                VALUES(1,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                  payload_json=excluded.payload_json,
                  expires_at=excluded.expires_at,
                  updated_at=excluded.updated_at
                """,
                (
                    json.dumps(token, sort_keys=True),
                    expires_at,
                    int(time.time()),
                ),
            )

    def create_pending(
        self,
        *,
        state: str,
        code_verifier: str,
        redirect_uri: str,
        ttl_seconds: int = 900,
    ) -> None:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM oauth_pending")
            connection.execute(
                """
                INSERT INTO oauth_pending(
                    state,code_verifier,redirect_uri,expires_at,created_at
                ) VALUES(?,?,?,?,?)
                """,
                (
                    state,
                    code_verifier,
                    redirect_uri,
                    now + ttl_seconds,
                    now,
                ),
            )

    def consume_pending(self, state: str) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state,code_verifier,redirect_uri,expires_at
                FROM oauth_pending
                WHERE state = ?
                """,
                (state,),
            ).fetchone()
            if row is None or int(row["expires_at"]) < now:
                raise DnsFilterMcpOAuthError(
                    "DNSFilter OAuth transaction is missing or expired."
                )
            connection.execute(
                "DELETE FROM oauth_pending WHERE state = ?",
                (state,),
            )
        return dict(row)

    def clear_token(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM oauth_token")
            connection.execute("DELETE FROM oauth_pending")

    def status(self) -> DnsFilterOAuthStatus:
        registration = self.get_registration()
        token = self.get_token()
        expires_at = int(token.get("_expires_at")) if token and token.get("_expires_at") else None
        now = int(time.time())
        connected = bool(
            token
            and token.get("access_token")
            and (expires_at is None or expires_at > now)
        )
        with self._connect() as connection:
            pending = connection.execute(
                "SELECT 1 FROM oauth_pending WHERE expires_at >= ? LIMIT 1",
                (now,),
            ).fetchone()
        return DnsFilterOAuthStatus(
            registered=registration is not None,
            connected=connected,
            expires_at=expires_at,
            has_refresh_token=bool(token and token.get("refresh_token")),
            pending_authorization=pending is not None,
        )


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    form: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    body = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }
    request_headers.update(headers or {})
    if payload is not None:
        body = json.dumps(dict(payload)).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    elif form is not None:
        body = urlencode(
            {k: v for k, v in form.items() if v is not None}
        ).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(
        url,
        data=body,
        method=method,
        headers=request_headers,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raise DnsFilterMcpOAuthError(
            f"DNSFilter OAuth HTTP request failed with status {exc.code}."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth HTTP request failed."
        ) from exc
    try:
        decoded = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth response was not valid JSON."
        ) from exc
    if not isinstance(decoded, dict):
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth response had an invalid shape."
        )
    return decoded


def discover_dnsfilter_oauth() -> dict[str, Any]:
    resource = _json_request(DNSFILTER_PROTECTED_RESOURCE_METADATA)
    servers = resource.get("authorization_servers")
    if servers != [DNSFILTER_MCP_RESOURCE]:
        raise DnsFilterMcpOAuthError(
            "DNSFilter protected-resource metadata returned an unexpected issuer."
        )
    metadata = _json_request(DNSFILTER_AUTHORIZATION_SERVER_METADATA)
    expected = {
        "issuer": DNSFILTER_MCP_RESOURCE,
        "authorization_endpoint": "https://mcp.dnsfilter.com/authorize",
        "token_endpoint": "https://mcp.dnsfilter.com/token",
        "registration_endpoint": "https://mcp.dnsfilter.com/register",
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise DnsFilterMcpOAuthError(
                f"DNSFilter OAuth metadata returned an unexpected {key}."
            )
    if "S256" not in (metadata.get("code_challenge_methods_supported") or []):
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth metadata does not advertise PKCE S256."
        )
    return metadata


def register_dnsfilter_oauth_client(
    store: DnsFilterMcpOAuthStore,
    *,
    redirect_uri: str = DNSFILTER_MCP_REDIRECT_URI_DEFAULT,
) -> dict[str, Any]:
    metadata = discover_dnsfilter_oauth()
    existing = store.get_registration()
    if existing and redirect_uri in (existing.get("redirect_uris") or []):
        return existing
    registered = _json_request(
        metadata["registration_endpoint"],
        method="POST",
        payload={
            "client_name": "Project Jason DNSFilter MCP",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": DNSFILTER_OAUTH_SCOPE,
        },
    )
    if not str(registered.get("client_id") or "").strip():
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth registration did not return a client_id."
        )
    registered.setdefault("redirect_uris", [redirect_uri])
    store.set_registration(registered)
    return registered


def begin_dnsfilter_oauth(
    store: DnsFilterMcpOAuthStore,
    *,
    redirect_uri: str = DNSFILTER_MCP_REDIRECT_URI_DEFAULT,
) -> str:
    metadata = discover_dnsfilter_oauth()
    registration = register_dnsfilter_oauth_client(
        store,
        redirect_uri=redirect_uri,
    )
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(32)
    store.create_pending(
        state=state,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": registration["client_id"],
            "redirect_uri": redirect_uri,
            "scope": DNSFILTER_OAUTH_SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": DNSFILTER_MCP_RESOURCE,
        }
    )
    return f"{metadata['authorization_endpoint']}?{query}"


def complete_dnsfilter_oauth(
    store: DnsFilterMcpOAuthStore,
    *,
    code: str,
    state: str,
    iss: str | None = None,
) -> DnsFilterOAuthStatus:
    if not code or not state:
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth callback is missing code or state."
        )
    metadata = discover_dnsfilter_oauth()
    if iss and iss.rstrip("/") + "/" != metadata["issuer"]:
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth callback issuer did not match discovery."
        )
    pending = store.consume_pending(state)
    registration = store.get_registration()
    if not registration:
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth client registration is missing."
        )
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending["redirect_uri"],
        "client_id": registration["client_id"],
        "code_verifier": pending["code_verifier"],
        "resource": DNSFILTER_MCP_RESOURCE,
    }
    token = _token_request(metadata["token_endpoint"], registration, form)
    _require_token(token)
    store.set_token(token)
    return store.status()


def access_token(
    store: DnsFilterMcpOAuthStore,
    *,
    refresh_margin_seconds: int = 90,
) -> str:
    token = store.get_token()
    if not token:
        raise DnsFilterMcpOAuthError(
            "DNSFilter MCP OAuth connection is not established."
        )
    expires_at = token.get("_expires_at")
    if (
        token.get("access_token")
        and (
            expires_at is None
            or int(expires_at) > int(time.time()) + refresh_margin_seconds
        )
    ):
        return str(token["access_token"])
    refresh = str(token.get("refresh_token") or "").strip()
    if not refresh:
        raise DnsFilterMcpOAuthError(
            "DNSFilter MCP OAuth session requires re-authentication."
        )
    registration = store.get_registration()
    if not registration:
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth client registration is missing."
        )
    metadata = discover_dnsfilter_oauth()
    refreshed = _token_request(
        metadata["token_endpoint"],
        registration,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": registration["client_id"],
            "scope": DNSFILTER_OAUTH_SCOPE,
            "resource": DNSFILTER_MCP_RESOURCE,
        },
    )
    _require_token(refreshed)
    if not refreshed.get("refresh_token"):
        refreshed["refresh_token"] = refresh
    store.set_token(refreshed)
    return str(refreshed["access_token"])


def _token_request(
    token_endpoint: str,
    registration: Mapping[str, Any],
    form: Mapping[str, Any],
) -> dict[str, Any]:
    method = str(
        registration.get("token_endpoint_auth_method") or "none"
    )
    headers: dict[str, str] = {}
    values = dict(form)
    client_secret = str(registration.get("client_secret") or "")
    if method == "client_secret_basic" and client_secret:
        raw = (
            f"{registration['client_id']}:{client_secret}".encode("utf-8")
        )
        headers["Authorization"] = (
            "Basic "
            + base64.b64encode(raw).decode("ascii")
        )
    elif method == "client_secret_post" and client_secret:
        values["client_secret"] = client_secret
    elif method not in {"none", "client_secret_basic", "client_secret_post"}:
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth client uses an unsupported token auth method."
        )
    return _json_request(
        token_endpoint,
        method="POST",
        form=values,
        headers=headers,
    )


def _require_token(token: Mapping[str, Any]) -> None:
    if not str(token.get("access_token") or "").strip():
        raise DnsFilterMcpOAuthError(
            "DNSFilter OAuth token response did not include an access token."
        )


def _token_expires_at(token: Mapping[str, Any]) -> int | None:
    now = int(time.time())
    expires_in = token.get("expires_in")
    try:
        if expires_in is not None:
            return now + max(1, int(expires_in))
    except (TypeError, ValueError):
        pass
    access = str(token.get("access_token") or "")
    pieces = access.split(".")
    if len(pieces) >= 2:
        try:
            payload = pieces[1] + "=" * (-len(pieces[1]) % 4)
            decoded = json.loads(
                base64.urlsafe_b64decode(payload).decode("utf-8")
            )
            if decoded.get("exp") is not None:
                return int(decoded["exp"])
        except Exception:
            pass
    return None
