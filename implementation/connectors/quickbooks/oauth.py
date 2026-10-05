from __future__ import annotations

import base64
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

from connectors.core.contracts import ConnectorConfigurationError

QUICKBOOKS_AUTHORIZATION_URL = "https://appcenter.intuit.com/connect/oauth2"
QUICKBOOKS_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QUICKBOOKS_SCOPE = "com.intuit.quickbooks.accounting"
QUICKBOOKS_REDIRECT_URI_DEFAULT = (
    "https://mcp-jason.teamaot.com/oauth/quickbooks/callback"
)
QUICKBOOKS_OAUTH_DB_DEFAULT = Path(
    "/var/lib/jason/openclaw/quickbooks/oauth.sqlite3"
)
QUICKBOOKS_ENVIRONMENTS = frozenset({"sandbox", "production"})


class QuickBooksOAuthError(RuntimeError):
    """Safe OAuth failure that must never echo credentials or tokens."""


@dataclass(frozen=True, slots=True)
class QuickBooksOAuthStatus:
    connected: bool
    environment: str | None
    realm_id: str | None
    expires_at: int | None
    has_refresh_token: bool
    pending_authorization: bool


class QuickBooksOAuthStore:
    """Protected rotating OAuth state for one authorized QuickBooks company.

    Static Intuit app credentials are intentionally not stored here. They remain in
    OpenBao. This store contains the provider-issued rotating access/refresh tokens,
    the server-derived Realm ID, environment, and short-lived authorization state.
    """

    def __init__(self, path: Path = QUICKBOOKS_OAUTH_DB_DEFAULT) -> None:
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
        with self._raw_connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_token (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    payload_json TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    realm_id TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_pending (
                    state TEXT PRIMARY KEY,
                    redirect_uri TEXT NOT NULL,
                    environment TEXT NOT NULL,
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
        self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        self._ensure_initialized()
        return self._raw_connect()

    def create_pending(
        self,
        *,
        state: str,
        redirect_uri: str,
        environment: str,
        ttl_seconds: int = 900,
    ) -> None:
        _require_environment(environment)
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM oauth_pending")
            connection.execute(
                """
                INSERT INTO oauth_pending(
                    state,redirect_uri,environment,expires_at,created_at
                ) VALUES(?,?,?,?,?)
                """,
                (state, redirect_uri, environment, now + ttl_seconds, now),
            )

    def consume_pending(self, state: str) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state,redirect_uri,environment,expires_at
                FROM oauth_pending
                WHERE state = ?
                """,
                (state,),
            ).fetchone()
            if row is None or int(row["expires_at"]) < now:
                raise QuickBooksOAuthError(
                    "QuickBooks OAuth transaction is missing or expired."
                )
            connection.execute(
                "DELETE FROM oauth_pending WHERE state = ?",
                (state,),
            )
        return dict(row)

    def get_token(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json,expires_at,realm_id,environment
                FROM oauth_token
                WHERE singleton = 1
                """
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["_expires_at"] = int(row["expires_at"])
        payload["_realm_id"] = str(row["realm_id"])
        payload["_environment"] = str(row["environment"])
        return payload

    def set_token(
        self,
        payload: Mapping[str, Any],
        *,
        realm_id: str,
        environment: str,
    ) -> None:
        _require_environment(environment)
        realm = _require_realm_id(realm_id)
        token = dict(payload)
        access_token = str(token.get("access_token") or "").strip()
        refresh_token = str(token.get("refresh_token") or "").strip()
        if not access_token or not refresh_token:
            raise QuickBooksOAuthError(
                "QuickBooks token response did not contain required tokens."
            )
        try:
            expires_in = int(token.get("expires_in") or 0)
        except (TypeError, ValueError) as exc:
            raise QuickBooksOAuthError(
                "QuickBooks token response contained an invalid expiration."
            ) from exc
        if expires_in <= 0:
            raise QuickBooksOAuthError(
                "QuickBooks token response did not contain a valid expiration."
            )
        expires_at = int(time.time()) + expires_in
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO oauth_token(
                    singleton,payload_json,expires_at,realm_id,environment,updated_at
                ) VALUES(1,?,?,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    expires_at=excluded.expires_at,
                    realm_id=excluded.realm_id,
                    environment=excluded.environment,
                    updated_at=excluded.updated_at
                """,
                (
                    json.dumps(token, sort_keys=True),
                    expires_at,
                    realm,
                    environment,
                    int(time.time()),
                ),
            )

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM oauth_token")
            connection.execute("DELETE FROM oauth_pending")

    def status(self) -> QuickBooksOAuthStatus:
        token = self.get_token()
        now = int(time.time())
        with self._connect() as connection:
            pending = connection.execute(
                "SELECT 1 FROM oauth_pending WHERE expires_at >= ? LIMIT 1",
                (now,),
            ).fetchone()
        return QuickBooksOAuthStatus(
            connected=bool(
                token
                and token.get("access_token")
                and int(token.get("_expires_at") or 0) > now
            ),
            environment=(
                str(token.get("_environment")) if token else None
            ),
            realm_id=(str(token.get("_realm_id")) if token else None),
            expires_at=(int(token.get("_expires_at")) if token else None),
            has_refresh_token=bool(token and token.get("refresh_token")),
            pending_authorization=pending is not None,
        )


def _require_environment(environment: str) -> str:
    value = str(environment or "").strip().casefold()
    if value not in QUICKBOOKS_ENVIRONMENTS:
        raise ConnectorConfigurationError(
            "QuickBooks environment must be sandbox or production."
        )
    return value


def _require_realm_id(realm_id: str) -> str:
    value = str(realm_id or "").strip()
    if not value.isdigit():
        raise QuickBooksOAuthError("QuickBooks Realm ID is invalid.")
    return value


def _require_client_credentials(
    credentials: Mapping[str, str],
) -> tuple[str, str]:
    client_id = str(credentials.get("client_id") or "").strip()
    client_secret = str(credentials.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise ConnectorConfigurationError(
            "QuickBooks OAuth client credentials are unavailable."
        )
    return client_id, client_secret


def begin_quickbooks_oauth(
    store: QuickBooksOAuthStore,
    *,
    client_id: str,
    environment: str = "sandbox",
    redirect_uri: str = QUICKBOOKS_REDIRECT_URI_DEFAULT,
) -> str:
    environment = _require_environment(environment)
    client_id = str(client_id or "").strip()
    redirect_uri = str(redirect_uri or "").strip()
    if not client_id or not redirect_uri:
        raise QuickBooksOAuthError(
            "QuickBooks OAuth client ID and redirect URI are required."
        )
    state = secrets.token_urlsafe(32)
    store.create_pending(
        state=state,
        redirect_uri=redirect_uri,
        environment=environment,
    )
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": QUICKBOOKS_SCOPE,
            "state": state,
        }
    )
    return f"{QUICKBOOKS_AUTHORIZATION_URL}?{query}"


def _token_request(
    *,
    client_id: str,
    client_secret: str,
    form: Mapping[str, str],
) -> dict[str, Any]:
    basic = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        QUICKBOOKS_TOKEN_URL,
        data=urlencode(dict(form)).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic}",
        },
    )
    try:
        with urlopen(request, timeout=30.0) as response:
            raw = response.read()
    except HTTPError as exc:
        raise QuickBooksOAuthError(
            f"QuickBooks OAuth token request failed with status {exc.code}."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise QuickBooksOAuthError(
            "QuickBooks OAuth token request failed."
        ) from exc
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuickBooksOAuthError(
            "QuickBooks OAuth token response was not valid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise QuickBooksOAuthError(
            "QuickBooks OAuth token response had an invalid shape."
        )
    return payload


def complete_quickbooks_oauth(
    store: QuickBooksOAuthStore,
    *,
    credentials: Mapping[str, str],
    code: str,
    state: str,
    realm_id: str,
) -> QuickBooksOAuthStatus:
    code = str(code or "").strip()
    state = str(state or "").strip()
    if not code or not state:
        raise QuickBooksOAuthError(
            "QuickBooks OAuth callback is missing code or state."
        )
    pending = store.consume_pending(state)
    client_id, client_secret = _require_client_credentials(credentials)
    payload = _token_request(
        client_id=client_id,
        client_secret=client_secret,
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": str(pending["redirect_uri"]),
        },
    )
    store.set_token(
        payload,
        realm_id=_require_realm_id(realm_id),
        environment=str(pending["environment"]),
    )
    return store.status()


def refresh_quickbooks_oauth(
    store: QuickBooksOAuthStore,
    *,
    credentials: Mapping[str, str],
) -> QuickBooksOAuthStatus:
    current = store.get_token()
    if current is None:
        raise QuickBooksOAuthError("QuickBooks is not connected.")
    refresh_token = str(current.get("refresh_token") or "").strip()
    if not refresh_token:
        raise QuickBooksOAuthError(
            "QuickBooks refresh token is unavailable."
        )
    client_id, client_secret = _require_client_credentials(credentials)
    payload = _token_request(
        client_id=client_id,
        client_secret=client_secret,
        form={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    store.set_token(
        payload,
        realm_id=str(current["_realm_id"]),
        environment=str(current["_environment"]),
    )
    return store.status()


def quickbooks_access_context(
    store: QuickBooksOAuthStore,
    *,
    credentials: Mapping[str, str],
    refresh_window_seconds: int = 120,
) -> tuple[str, str, str]:
    token = store.get_token()
    if token is None:
        raise QuickBooksOAuthError("QuickBooks is not connected.")
    if int(token.get("_expires_at") or 0) <= int(time.time()) + refresh_window_seconds:
        refresh_quickbooks_oauth(store, credentials=credentials)
        token = store.get_token()
    if token is None:
        raise QuickBooksOAuthError("QuickBooks OAuth state is unavailable.")
    access_token = str(token.get("access_token") or "").strip()
    realm_id = _require_realm_id(str(token.get("_realm_id") or ""))
    environment = _require_environment(str(token.get("_environment") or ""))
    if not access_token:
        raise QuickBooksOAuthError("QuickBooks access token is unavailable.")
    return access_token, realm_id, environment
