#!/usr/bin/env python3
"""OpenClaw KFS collector.

Read-only Kyocera Fleet Services collector that:
- logs in once
- fetches GroupList and DeviceList per group
- fetches DeviceLogList per group for device fault/event history
- stores raw responses on disk
- writes normalized append-only history to PostgreSQL

The collector is intentionally conservative:
- one login attempt per run
- no mutation endpoints
- no retries on auth failure
- secrets are loaded from OpenClaw secure config or environment variables
"""

from __future__ import annotations

import argparse
import base64
import copy
import dataclasses
import hashlib
import http.cookiejar
import json
import os
import re
import ssl
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = WORKSPACE_ROOT / "Temp" / "KFS-Collector"
DEFAULT_SECRETS_PATH = Path.home() / ".openclaw" / "secrets.json"
DEFAULT_FALLBACK_SECRETS_PATH = Path("/etc/openclaw/secrets.json")
DEFAULT_BASE_URL = "https://api.kyods.com"
DEFAULT_REQUEST_TO = "KFS_US"
DEFAULT_TIMEOUT = 120
DEFAULT_SCOPE = 1
DEFAULT_SOURCE = "OpenClaw KFS Collector"

GROUP_ATTR_IDS = [
    "groupName",
    "groupType",
    "registrationId",
    "customerName",
    "customerId",
    "totalDeviceCount",
    "managedDeviceCount",
]

DEVICE_ATTR_IDS = [
    "manufacturer",
    "modelName",
    "serialNumber",
    "hostname",
    "ipAddress",
    "macAddress",
    "equipmentId",
    "location",
    "assetNumber",
    "managementStatus",
    "deviceStatus",
    "customerID",
    "customerName",
    "lastUpdate",
    "blackTonerLevel",
    "cyanTonerLevel",
    "magentaTonerLevel",
    "yellowTonerLevel",
    "wasteTonerStatus",
    "blackOEMPartNumber",
    "cyanOEMPartNumber",
    "magentaOEMPartNumber",
    "yellowOEMPartNumber",
    "blackTonerSerialNumber",
    "cyanTonerSerialNumber",
    "magentaTonerSerialNumber",
    "yellowTonerSerialNumber",
    "tonerReplacementPrediction",
    "replacementTimeTonerLevels",
    "maintenanceKit",
]

COUNTER_ATTR_IDS = [
    "total",
    "blackWhite",
    "color",
    "fullColor",
    "printerTotal",
    "printerBw",
    "printerColorTotal",
    "copierTotal",
    "copierBw",
    "copierColorTotal",
    "scanTotal",
    "faxTotal",
    "lifecountTotal",
    "letterTotal",
    "legalTotal",
    "ledgerTotal",
    "a3Total",
    "a4Total",
    "simplexTotal",
    "duplexTotal",
]

COUNTER_FIELD_ALIASES = {
    "total": ["total", "meterTotal", "countTotal"],
    "blackwhite": ["blackWhite", "bw", "blackWhiteMeter"],
    "color": ["color", "colorMeter"],
    "fullcolor": ["fullColor", "fullColorMeter"],
    "printertotal": ["printerTotal"],
    "printerbw": ["printerBw", "printerBW", "printerBlackWhite"],
    "printercolortotal": ["printerColorTotal"],
    "copiertotal": ["copierTotal"],
    "copierbw": ["copierBw", "copierBW"],
    "copiercolortotal": ["copierColorTotal"],
    "scantotal": ["scanTotal"],
    "faxtotal": ["faxTotal"],
    "lifecounttotal": ["lifecountTotal", "lifeCountTotal", "lifeCount"],
    "lettertotal": ["letterTotal"],
    "legaltotal": ["legalTotal"],
    "ledgertotal": ["ledgerTotal"],
    "a3total": ["a3Total"],
    "a4total": ["a4Total"],
    "simplextotal": ["simplexTotal"],
    "duplextotal": ["duplexTotal"],
}

RUN_DELTA_COUNTER_FIELDS = [
    "total_meter",
    "black_white_meter",
    "color_meter",
    "full_color_meter",
    "copier_total",
    "copier_bw",
    "copier_color_total",
    "printer_total",
    "printer_bw",
    "printer_color_total",
    "scan_total",
    "fax_total",
    "life_count_total",
]

RUN_DELTA_CONSUMABLE_FIELDS = [
    "black_toner_level",
    "cyan_toner_level",
    "magenta_toner_level",
    "yellow_toner_level",
    "waste_toner_status",
]

RUN_DELTA_STATUS_FIELDS = [
    "management_status",
    "device_status",
    "last_update_raw",
]


@dataclasses.dataclass(slots=True)
class KfsConfig:
    base_url: str = DEFAULT_BASE_URL
    request_from: str = ""
    request_to: str = DEFAULT_REQUEST_TO
    auth_token: str = ""
    access_id: str = ""
    access_password: str = ""
    username: str = ""
    password: str = ""
    database_url: str = ""
    source: str = DEFAULT_SOURCE
    timeout_sec: int = DEFAULT_TIMEOUT
    scope: int = DEFAULT_SCOPE
    extra_headers: dict[str, str] = dataclasses.field(default_factory=dict)
    output_root: Path = DEFAULT_OUTPUT_ROOT
    secrets_path: Path = DEFAULT_SECRETS_PATH
    dry_run: bool = False


class KfsError(RuntimeError):
    pass


class KfsAuthError(KfsError):
    pass


class ArtifactWriter:
    def __init__(self, output_root: Path) -> None:
        self.run_root = output_root
        self.requests_dir = output_root / "requests"
        self.responses_dir = output_root / "responses"
        self.logs_dir = output_root / "logs"
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.logs_dir / "collector.log"
        self.summary_path = output_root / "summary.json"
        self.manifest_path = output_root / "manifest.json"
        self.sequence = 0

    def next_name(self, slug: str) -> str:
        self.sequence += 1
        return f"{self.sequence:03d}_{slug}"

    def log(self, message: str) -> None:
        line = f"[{utc_now().isoformat()}] {message}"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, flush=True)

    def write_text(self, rel_path: Path, text: str) -> Path:
        path = self.run_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_json(self, rel_path: Path, value: Any) -> Path:
        return self.write_text(rel_path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))

    def write_exchange(
        self,
        slug: str,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        name = self.next_name(slug)
        self.write_json(Path("requests") / f"{name}.json", request)
        self.write_json(Path("responses") / f"{name}.headers.json", response["headers"])
        self.write_text(Path("responses") / f"{name}.body.txt", response["raw_text"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime:
    if not value:
        return utc_now()
    if value.endswith("Z"):
        return datetime.fromisoformat(value[:-1] + "+00:00")
    return datetime.fromisoformat(value)


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def unique_paths(paths: Iterable[Path | None]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for item in paths:
        if item is None:
            continue
        resolved = item.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = normalize_string(value)
    if not text:
        return None
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def normalize_raw_bigint(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = normalize_string(value)
    if not text:
        return None
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except ValueError:
            return None
    return None


def normalize_timestamp(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if abs(stamp) > 10_000_000_000:
            stamp /= 1000.0
        try:
            return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
        except Exception:
            return None
    text = normalize_string(value)
    if not text:
        return None
    if re.fullmatch(r"-?\d+", text):
        try:
            stamp = float(int(text))
            if abs(stamp) > 10_000_000_000:
                stamp /= 1000.0
            return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
        except Exception:
            return text
    try:
        return parse_dt(text).astimezone(timezone.utc).isoformat()
    except Exception:
        return text


def stable_text_key(*parts: Any) -> str:
    text = "|".join(normalize_string(part) for part in parts if normalize_string(part))
    if text:
        return text
    digest = hashlib.sha1(repr(parts).encode("utf-8")).hexdigest()
    return f"derived:{digest[:16]}"


def slugify(value: Any) -> str:
    text = normalize_string(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"


def load_first_json_path(candidates: Sequence[Path]) -> tuple[dict[str, Any], Path] | tuple[None, None]:
    for path in candidates:
        if path.exists():
            return load_json_file(path), path
    return None, None


def deep_pick(obj: Any, *paths: str) -> Any:
    for path in paths:
        if not path:
            continue
        current = obj
        ok = True
        for segment in path.split("."):
            if current is None:
                ok = False
                break
            if isinstance(current, dict):
                match = None
                for key, value in current.items():
                    if str(key).lower() == segment.lower():
                        match = value
                        break
                if match is None:
                    ok = False
                    break
                current = match
            elif isinstance(current, list):
                found = None
                for item in current:
                    candidate = deep_pick(item, segment)
                    if candidate is not None:
                        found = candidate
                        break
                if found is None:
                    ok = False
                    break
                current = found
            else:
                ok = False
                break
        if ok and current is not None and normalize_string(current) != "":
            return current
    return None


def iter_objects(value: Any) -> Iterator[Any]:
    if isinstance(value, list):
        for item in value:
            yield from iter_objects(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from iter_objects(item)


def find_collection(body: Any, preferred_keys: Sequence[str]) -> list[Any]:
    if body is None:
        return []
    if isinstance(body, list):
        return list(body)
    if isinstance(body, dict):
        for key in preferred_keys:
            candidate = deep_pick(body, key)
            if isinstance(candidate, list):
                return list(candidate)
        for candidate in body.values():
            if isinstance(candidate, list) and candidate:
                if all(isinstance(item, (dict, list)) for item in candidate):
                    return list(candidate)
        if any(k.lower() in {"groupid", "deviceid", "id"} for k in body.keys()):
            return [body]
    return []


def extract_status_code(body: Any) -> int | None:
    value = deep_pick(
        body,
        "status.code",
        "Status.code",
        "result.status.code",
        "response.status.code",
        "body.status.code",
        "meta.status.code",
    )
    return normalize_int(value)


def extract_status_message(body: Any) -> str | None:
    value = deep_pick(
        body,
        "status.messageResource",
        "status.message",
        "status.msg",
        "Status.message",
        "Status.msg",
        "message",
        "error.message",
        "result.message",
        "response.message",
        "body.message",
    )
    text = normalize_string(value)
    return text or None


def extract_collection(body: Any, preferred_keys: Sequence[str]) -> list[Any]:
    return find_collection(body, preferred_keys)


def sanitize_recursive(value: Any, secrets: Sequence[str]) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_recursive(val, secrets) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_recursive(item, secrets) for item in value]
    if isinstance(value, str):
        text = value
        for secret in secrets:
            if secret:
                text = text.replace(secret, "<redacted>")
                if secret.lower().startswith("basic "):
                    text = text.replace(secret[6:], "<redacted>")
        return text
    return value


def mask_text(text: str, secrets: Sequence[str]) -> str:
    masked = text
    for secret in secrets:
        if secret:
            masked = masked.replace(secret, "<redacted>")
    return masked


def merge_config_dict(source: dict[str, Any], target: KfsConfig) -> None:
    def pick(*names: str) -> Any:
        for name in names:
            for key, value in source.items():
                if str(key).lower() == name.lower() and value not in (None, ""):
                    return value
        return None

    target.base_url = normalize_string(
        pick("base_url", "baseurl", "kfs_base_url") or target.base_url
    )
    target.request_from = normalize_string(
        pick("request_from", "requestfrom", "kfs_request_from") or target.request_from
    )
    target.request_to = normalize_string(
        pick("request_to", "requestto", "kfs_request_to") or target.request_to
    )
    target.auth_token = normalize_string(
        pick(
            "auth_token",
            "authorization_token",
            "basic_authorization",
            "kfs_auth_token",
            "kfs_basic_authorization",
        )
        or target.auth_token
    )
    target.access_id = normalize_string(
        pick("access_id", "accessid", "kfs_access_id", "id") or target.access_id
    )
    target.access_password = normalize_string(
        pick("access_password", "accesspassword", "kfs_access_password", "password") or target.access_password
    )
    target.username = normalize_string(
        pick("username", "login_id", "loginid", "kfs_username", "kfs_login_id") or target.username
    )
    target.password = normalize_string(
        pick("password", "login_password", "loginpassword", "kfs_password", "kfs_login_password")
        or target.password
    )
    target.database_url = normalize_string(
        pick("database_url", "postgres_url", "kfs_database_url") or target.database_url
    )
    target.source = normalize_string(pick("source", "collector_source") or target.source)
    if normalize_int(pick("timeout_sec", "timeout")) is not None:
        target.timeout_sec = normalize_int(pick("timeout_sec", "timeout")) or target.timeout_sec
    if normalize_int(pick("scope")) is not None:
        target.scope = normalize_int(pick("scope")) or target.scope

    extra_headers = pick("extra_headers", "extraheaders")
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            text = normalize_string(value)
            if text:
                target.extra_headers[str(key)] = text
        target.username = normalize_string(
            extra_headers.get("ID") or extra_headers.get("Id") or extra_headers.get("id") or target.username
        )
        target.password = normalize_string(
            extra_headers.get("Password")
            or extra_headers.get("password")
            or target.password
        )


def load_config(args: argparse.Namespace) -> KfsConfig:
    config = KfsConfig()

    config_candidates = unique_paths(
        [
            Path(args.config).expanduser() if args.config else None,
            Path(os.environ["KFS_CONFIG_PATH"]).expanduser() if os.environ.get("KFS_CONFIG_PATH") else None,
            Path(os.environ["OPENCLAW_SECRETS_PATH"]).expanduser()
            if os.environ.get("OPENCLAW_SECRETS_PATH")
            else None,
            DEFAULT_SECRETS_PATH,
            DEFAULT_FALLBACK_SECRETS_PATH,
        ]
    )

    config_json, config_path = load_first_json_path(config_candidates)
    if config_json is not None:
        section = (
            config_json.get("kfs")
            or config_json.get("kyocera_fleet_services")
            or config_json.get("kyocera")
            or config_json
        )
        if isinstance(section, dict):
            merge_config_dict(section, config)
        if config_path is not None:
            config.secrets_path = config_path

    env_map = {
        "KFS_BASE_URL": "base_url",
        "KFS_REQUEST_FROM": "request_from",
        "KFS_REQUEST_TO": "request_to",
        "KFS_AUTH_TOKEN": "auth_token",
        "KFS_BASIC_AUTHORIZATION": "auth_token",
        "KFS_ACCESS_ID": "access_id",
        "KFS_ACCESS_PASSWORD": "access_password",
        "KFS_USERNAME": "username",
        "KFS_USER": "username",
        "KFS_LOGIN_ID": "username",
        "KFS_PASSWORD": "password",
        "KFS_LOGIN_PASSWORD": "password",
        "DATABASE_URL": "database_url",
        "KFS_SOURCE": "source",
        "KFS_TIMEOUT_SEC": "timeout_sec",
        "KFS_SCOPE": "scope",
        "KFS_OUTPUT_ROOT": "output_root",
        "KFS_SECRETS_PATH": "secrets_path",
    }
    for env_name, attr in env_map.items():
        value = os.environ.get(env_name)
        if not value:
            continue
        if attr == "timeout_sec":
            config.timeout_sec = normalize_int(value) or config.timeout_sec
        elif attr == "scope":
            config.scope = normalize_int(value) or config.scope
        elif attr == "output_root":
            config.output_root = Path(value).expanduser()
        elif attr == "secrets_path":
            config.secrets_path = Path(value).expanduser()
        else:
            setattr(config, attr, normalize_string(value))

    if args.base_url:
        config.base_url = args.base_url
    if args.request_from:
        config.request_from = args.request_from
    if args.request_to:
        config.request_to = args.request_to
    if args.auth_token:
        config.auth_token = args.auth_token
    if args.access_id:
        config.access_id = args.access_id
    if args.access_password:
        config.access_password = args.access_password
    if args.username:
        config.username = args.username
    if args.password:
        config.password = args.password
    if args.database_url:
        config.database_url = args.database_url
    if args.output_root:
        config.output_root = Path(args.output_root).expanduser()
    if args.secrets_path:
        config.secrets_path = Path(args.secrets_path).expanduser()
    if args.timeout_sec:
        config.timeout_sec = args.timeout_sec
    if args.scope:
        config.scope = args.scope
    if args.source:
        config.source = args.source

    config.dry_run = args.dry_run
    if not config.request_to:
        config.request_to = DEFAULT_REQUEST_TO
    if not config.base_url:
        config.base_url = DEFAULT_BASE_URL
    return config


def normalize_auth_token(token: str) -> str:
    text = normalize_string(token)
    if not text:
        return ""
    if text.lower().startswith("basic "):
        text = text[6:].strip()
    return text


def build_basic_token(config: KfsConfig) -> str:
    token = normalize_auth_token(config.auth_token)
    if token:
        return token
    if config.access_id and config.access_password:
        raw = f"{config.access_id}:{config.access_password}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")
    return ""


class KfsHttpClient:
    def __init__(self, config: KfsConfig, writer: ArtifactWriter) -> None:
        self.config = config
        self.writer = writer
        self.cookie_jar = http.cookiejar.CookieJar()
        self.ssl_context = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPSHandler(context=self.ssl_context),
        )
        self.opener.addheaders = [("User-Agent", "OpenClaw-KFS-Collector/1.0")]
        self.secrets = self.build_redaction_list()

    def build_redaction_list(self) -> list[str]:
        secrets = [
            self.config.auth_token,
            self.config.access_id,
            self.config.access_password,
            self.config.username,
            self.config.password,
        ]
        secrets.extend(self.config.extra_headers.values())
        if self.config.request_from:
            secrets.append(self.config.request_from)
        if self.config.request_to:
            secrets.append(self.config.request_to)
        return [item for item in secrets if item]

    def request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + endpoint
        body_bytes = None
        request_headers = self.build_headers()
        if payload is not None:
            body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body_bytes, method=method.upper())
        for key, value in request_headers.items():
            req.add_header(key, value)

        try:
            with self.opener.open(req, timeout=self.config.timeout_sec) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                raw = resp.read().decode("utf-8", errors="replace")
                headers = {name: value for name, value in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
            headers = {name: value for name, value in exc.headers.items()}

        parsed = try_parse_json(raw)
        body_status_code = extract_status_code(parsed)
        body_status_message = extract_status_message(parsed)
        body_for_storage: Any = parsed if parsed is not None else {"raw_text": raw}
        response = {
            "url": url,
            "status": status,
            "headers": headers,
            "raw_text": raw,
            "parsed": parsed,
            "body_status_code": body_status_code,
            "body_status_message": body_status_message,
            "body_for_storage": body_for_storage,
            "group_id": group_id,
        }
        return response

    def build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
            "User-Agent": "OpenClaw-KFS-Collector/1.0",
            "x-api-version": "6",
        }
        token = build_basic_token(self.config)
        if token:
            headers["Authorization"] = f"Basic {token}"
        for key, value in self.config.extra_headers.items():
            lowered = key.strip().lower()
            if lowered in {"id", "password", "accessid", "accesspassword", "authorization"}:
                continue
            if key not in headers and value:
                headers[key] = value
        return headers

    def log_request(self, slug: str, payload: dict[str, Any] | None, response: dict[str, Any]) -> None:
        safe_payload = sanitize_recursive(copy.deepcopy(payload), self.secrets) if payload is not None else None
        safe_headers = sanitize_recursive(copy.deepcopy(self.build_headers()), self.secrets)
        safe_response_headers = sanitize_recursive(copy.deepcopy(response["headers"]), self.secrets)
        self.writer.write_exchange(
            slug,
            {
                "method": "POST" if payload is not None else "GET",
                "url": response["url"],
                "headers": safe_headers,
                "body": safe_payload,
            },
            {
                "status": response["status"],
                "headers": safe_response_headers,
                "raw_text": response["raw_text"],
            },
        )


def try_parse_json(raw_text: str) -> Any | None:
    try:
        return json.loads(raw_text)
    except Exception:
        return None


def make_request_body(request_from: str, request_to: str, bodid: str, extra: dict[str, Any]) -> dict[str, Any]:
    body = {
        "RequestFrom": request_from or "",
        "RequestTo": request_to or DEFAULT_REQUEST_TO,
        "BODID": bodid,
    }
    body.update(extra)
    return body


def get_cookie_value(cookie_jar: http.cookiejar.CookieJar) -> str | None:
    cookie_parts: list[str] = []
    for cookie in cookie_jar:
        cookie_parts.append(f"{cookie.name}={cookie.value}")
    if not cookie_parts:
        return None
    return "; ".join(cookie_parts)


def get_first_non_empty(obj: Any, *paths: str) -> Any:
    value = deep_pick(obj, *paths)
    if value is None:
        return None
    if normalize_string(value) == "":
        return None
    return value


def extract_group_rows(body: Any) -> list[dict[str, Any]]:
    groups = extract_collection(body, ["groupList", "groups", "groupInfoList", "groupInfos", "data", "items"])
    rows: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        attribute = deep_pick(group, "attribute")
        if not isinstance(attribute, dict):
            attribute = {}
        row = {
            "group_id": normalize_string(get_first_non_empty(group, "groupId", "group.id", "id")),
            "group_name": normalize_string(
                get_first_non_empty(group, "groupName", "group.name", "name")
                or get_first_non_empty(attribute, "groupName", "group.name", "name")
            ),
            "group_type": normalize_int(
                get_first_non_empty(group, "groupType", "group.type")
                or get_first_non_empty(attribute, "groupType", "group.type")
            ),
            "registration_id": normalize_string(
                get_first_non_empty(group, "registrationId", "registration.id")
                or get_first_non_empty(attribute, "registrationId", "registration.id")
            ),
            "customer_name": normalize_string(
                get_first_non_empty(group, "customerName", "customer.name")
                or get_first_non_empty(attribute, "customerName", "customer.name")
            ),
            "customer_id": normalize_string(
                get_first_non_empty(group, "customerId", "customerID", "customer.id")
                or get_first_non_empty(attribute, "customerId", "customerID", "customer.id")
            ),
            "total_device_count": normalize_int(
                get_first_non_empty(group, "totalDeviceCount", "total.device.count")
                or get_first_non_empty(attribute, "totalDeviceCount", "total.device.count")
            ),
            "managed_device_count": normalize_int(
                get_first_non_empty(group, "managedDeviceCount", "managed.device.count")
                or get_first_non_empty(attribute, "managedDeviceCount", "managed.device.count")
            ),
        }
        if row["group_id"] or row["group_name"]:
            rows.append(row)
    return dedupe_by_key(rows, lambda item: item["group_id"] or item["group_name"])


def extract_device_rows(body: Any) -> list[dict[str, Any]]:
    devices = extract_collection(body, ["deviceList", "devices", "deviceInfoList", "deviceInfos", "data", "items"])
    rows: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        attributes = deep_pick(device, "attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        counters = deep_pick(device, "counter", "counters", "meter", "meters")
        if counters is None:
            counters = attributes or device
        row = {
            "device_id": normalize_string(
                get_first_non_empty(device, "deviceId", "deviceID", "id")
                or get_first_non_empty(attributes, "deviceId", "deviceID", "id")
                or stable_text_key(
                    get_first_non_empty(device, "serialNumber", "serial.number")
                    or get_first_non_empty(attributes, "serialNumber", "serial.number"),
                    get_first_non_empty(device, "equipmentId", "equipment.id")
                    or get_first_non_empty(attributes, "equipmentId", "equipment.id"),
                    get_first_non_empty(device, "hostname", "hostName", "network.hostname")
                    or get_first_non_empty(attributes, "hostname", "hostName", "network.hostname"),
                )
            ),
            "serial_number": normalize_string(
                get_first_non_empty(device, "serialNumber", "serial.number")
                or get_first_non_empty(attributes, "serialNumber", "serial.number")
            ),
            "equipment_id": normalize_string(
                get_first_non_empty(device, "equipmentId", "equipment.id")
                or get_first_non_empty(attributes, "equipmentId", "equipment.id")
            ),
            "asset_number": normalize_string(
                get_first_non_empty(device, "assetNumber", "asset.number")
                or get_first_non_empty(attributes, "assetNumber", "asset.number")
            ),
            "manufacturer": normalize_string(
                get_first_non_empty(device, "manufacturer", "maker")
                or get_first_non_empty(attributes, "manufacturer", "maker")
            ),
            "model_name": normalize_string(
                get_first_non_empty(device, "modelName", "model.name", "model")
                or get_first_non_empty(attributes, "modelName", "model.name", "model")
            ),
            "hostname": normalize_string(
                get_first_non_empty(device, "hostname", "hostName", "network.hostname")
                or get_first_non_empty(attributes, "hostname", "hostName", "network.hostname")
            ),
            "ip_address": normalize_string(
                get_first_non_empty(device, "ipAddress", "ip", "network.ipAddress")
                or get_first_non_empty(attributes, "ipAddress", "ip", "network.ipAddress")
            ),
            "mac_address": normalize_string(
                get_first_non_empty(device, "macAddress", "mac", "network.macAddress")
                or get_first_non_empty(attributes, "macAddress", "mac", "network.macAddress")
            ),
            "location": normalize_string(
                get_first_non_empty(device, "location", "locationName", "siteLocation")
                or get_first_non_empty(attributes, "location", "locationName", "siteLocation")
            ),
            "customer_id": normalize_string(
                get_first_non_empty(device, "customerId", "customerID", "customer.id")
                or get_first_non_empty(attributes, "customerId", "customerID", "customer.id")
            ),
            "customer_name": normalize_string(
                get_first_non_empty(device, "customerName", "customer.name")
                or get_first_non_empty(attributes, "customerName", "customer.name")
            ),
            "management_status": normalize_int(
                get_first_non_empty(device, "managementStatus", "management.status")
                or get_first_non_empty(attributes, "managementStatus", "management.status")
            ),
            "device_status": normalize_int(
                get_first_non_empty(device, "deviceStatus", "status", "device.status")
                or get_first_non_empty(attributes, "deviceStatus", "status", "device.status")
            ),
            "last_update_raw": normalize_raw_bigint(
                get_first_non_empty(device, "lastUpdate", "lastUpdateUtc", "lastCommunicationDate", "updatedAt")
                or get_first_non_empty(attributes, "lastUpdate", "lastUpdateUtc", "lastCommunicationDate", "updatedAt")
            ),
            "last_update_iso": normalize_timestamp(
                get_first_non_empty(device, "lastUpdate", "lastUpdateUtc", "lastCommunicationDate", "updatedAt")
                or get_first_non_empty(attributes, "lastUpdate", "lastUpdateUtc", "lastCommunicationDate", "updatedAt")
            ),
            "black_toner_level": normalize_int(
                get_first_non_empty(device, "blackTonerLevel", "toner.blackTonerLevel")
                or get_first_non_empty(attributes, "blackTonerLevel", "toner.blackTonerLevel")
            ),
            "cyan_toner_level": normalize_int(
                get_first_non_empty(device, "cyanTonerLevel", "toner.cyanTonerLevel")
                or get_first_non_empty(attributes, "cyanTonerLevel", "toner.cyanTonerLevel")
            ),
            "magenta_toner_level": normalize_int(
                get_first_non_empty(device, "magentaTonerLevel", "toner.magentaTonerLevel")
                or get_first_non_empty(attributes, "magentaTonerLevel", "toner.magentaTonerLevel")
            ),
            "yellow_toner_level": normalize_int(
                get_first_non_empty(device, "yellowTonerLevel", "toner.yellowTonerLevel")
                or get_first_non_empty(attributes, "yellowTonerLevel", "toner.yellowTonerLevel")
            ),
            "waste_toner_status": normalize_int(
                get_first_non_empty(device, "wasteTonerStatus", "toner.wasteTonerStatus")
                or get_first_non_empty(attributes, "wasteTonerStatus", "toner.wasteTonerStatus")
            ),
            "black_oem_part_number": normalize_string(
                get_first_non_empty(device, "blackOEMPartNumber", "toner.blackOEMPartNumber")
                or get_first_non_empty(attributes, "blackOEMPartNumber", "toner.blackOEMPartNumber")
            ),
            "cyan_oem_part_number": normalize_string(
                get_first_non_empty(device, "cyanOEMPartNumber", "toner.cyanOEMPartNumber")
                or get_first_non_empty(attributes, "cyanOEMPartNumber", "toner.cyanOEMPartNumber")
            ),
            "magenta_oem_part_number": normalize_string(
                get_first_non_empty(device, "magentaOEMPartNumber", "toner.magentaOEMPartNumber")
                or get_first_non_empty(attributes, "magentaOEMPartNumber", "toner.magentaOEMPartNumber")
            ),
            "yellow_oem_part_number": normalize_string(
                get_first_non_empty(device, "yellowOEMPartNumber", "toner.yellowOEMPartNumber")
                or get_first_non_empty(attributes, "yellowOEMPartNumber", "toner.yellowOEMPartNumber")
            ),
            "black_toner_serial_number": normalize_string(
                get_first_non_empty(device, "blackTonerSerialNumber", "toner.blackTonerSerialNumber")
                or get_first_non_empty(attributes, "blackTonerSerialNumber", "toner.blackTonerSerialNumber")
            ),
            "cyan_toner_serial_number": normalize_string(
                get_first_non_empty(device, "cyanTonerSerialNumber", "toner.cyanTonerSerialNumber")
                or get_first_non_empty(attributes, "cyanTonerSerialNumber", "toner.cyanTonerSerialNumber")
            ),
            "magenta_toner_serial_number": normalize_string(
                get_first_non_empty(device, "magentaTonerSerialNumber", "toner.magentaTonerSerialNumber")
                or get_first_non_empty(attributes, "magentaTonerSerialNumber", "toner.magentaTonerSerialNumber")
            ),
            "yellow_toner_serial_number": normalize_string(
                get_first_non_empty(device, "yellowTonerSerialNumber", "toner.yellowTonerSerialNumber")
                or get_first_non_empty(attributes, "yellowTonerSerialNumber", "toner.yellowTonerSerialNumber")
            ),
            "toner_replacement_prediction": normalize_string(
                get_first_non_empty(device, "tonerReplacementPrediction")
                or get_first_non_empty(attributes, "tonerReplacementPrediction")
            ),
            "replacement_time_toner_levels": normalize_string(
                get_first_non_empty(device, "replacementTimeTonerLevels")
                or get_first_non_empty(attributes, "replacementTimeTonerLevels")
            ),
            "maintenance_kit": normalize_string(
                get_first_non_empty(device, "maintenanceKit")
                or get_first_non_empty(attributes, "maintenanceKit")
            ),
            "counters": counters,
        }
        rows.append(row)
    return dedupe_by_key(rows, lambda item: item["device_id"])


def extract_device_log_rows(body: Any) -> list[dict[str, Any]]:
    devices = extract_collection(body, ["deviceList", "devices", "deviceInfoList", "deviceInfos", "data", "items"])
    rows: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        device_id = normalize_string(get_first_non_empty(device, "deviceId", "deviceID", "id"))
        serial_number = normalize_string(get_first_non_empty(device, "serialNumber", "serial.number"))
        group_id = normalize_string(get_first_non_empty(device, "groupId", "group.id"))
        logs = deep_pick(device, "logs", "logList", "deviceLogs")
        if not isinstance(logs, list):
            continue
        for log in logs:
            if not isinstance(log, dict):
                continue
            rows.append(
                {
                    "device_id": device_id,
                    "serial_number": serial_number,
                    "group_id": group_id,
                    "log_type": normalize_int(get_first_non_empty(log, "type", "logType", "severity")),
                    "log_detail": normalize_string(get_first_non_empty(log, "detail", "logDetail", "code")),
                    "log_description": normalize_string(get_first_non_empty(log, "description", "message", "logMessage")),
                    "log_counter": normalize_raw_bigint(get_first_non_empty(log, "counter")),
                    "event_started_at": normalize_timestamp(get_first_non_empty(log, "dateTime", "occurredAt", "createdAt")),
                    "event_ended_at": normalize_timestamp(get_first_non_empty(log, "endDateTime", "endedAt", "resolvedAt")),
                }
            )
    return rows


def dedupe_by_key(rows: Sequence[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        key = normalize_string(key_fn(row))
        if not key:
            continue
        if key not in seen:
            order.append(key)
            seen[key] = row
            continue
        existing = seen[key]
        for field, value in row.items():
            if normalize_string(existing.get(field)) == "" and normalize_string(value) != "":
                existing[field] = value
        seen[key] = existing
    return [seen[key] for key in order]


def build_counter_rows(
    run_id: str,
    reading_at: str,
    group: dict[str, Any],
    device: dict[str, Any],
) -> list[dict[str, Any]]:
    counters = device.get("counter") or device.get("counters")
    if counters is None and isinstance(device, dict):
        counters = device
    rows: list[dict[str, Any]] = []

    base = {
        "run_id": run_id,
        "reading_at": reading_at,
        "device_id": device["device_id"],
        "serial_number": device["serial_number"],
        "equipment_id": device["equipment_id"],
        "group_id": group.get("group_id") or "",
        "customer_id": device["customer_id"] or group.get("customer_id") or "",
        "customer_name": device["customer_name"] or group.get("customer_name") or "",
    }

    def add_counter(name: str, value: Any) -> None:
        count = normalize_int(value)
        if count is None:
            return
        rows.append(
            {
                **base,
                "counter_name": name,
                "counter_value": count,
            }
        )

    for field in COUNTER_ATTR_IDS:
        for alias in COUNTER_FIELD_ALIASES.get(field.lower(), [field]):
            value = get_first_non_empty(counters, alias)
            if value is not None:
                add_counter(field, value)
                break
    return rows


def build_consumable_rows(
    run_id: str,
    reading_at: str,
    group: dict[str, Any],
    device: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    color_specs = [
        (
            "black",
            device.get("black_toner_level"),
            device.get("black_oem_part_number"),
            device.get("black_toner_serial_number"),
        ),
        (
            "cyan",
            device.get("cyan_toner_level"),
            device.get("cyan_oem_part_number"),
            device.get("cyan_toner_serial_number"),
        ),
        (
            "magenta",
            device.get("magenta_toner_level"),
            device.get("magenta_oem_part_number"),
            device.get("magenta_toner_serial_number"),
        ),
        (
            "yellow",
            device.get("yellow_toner_level"),
            device.get("yellow_oem_part_number"),
            device.get("yellow_toner_serial_number"),
        ),
    ]
    for color, level, part_number, serial_number in color_specs:
        if level is None and not part_number and not serial_number:
            continue
        rows.append(
            {
                "run_id": run_id,
                "reading_at": reading_at,
                "device_id": device["device_id"],
                "serial_number": device["serial_number"],
                "equipment_id": device["equipment_id"],
                "group_id": group.get("group_id") or "",
                "customer_id": device["customer_id"] or group.get("customer_id") or "",
                "customer_name": device["customer_name"] or group.get("customer_name") or "",
                "consumable_type": "toner",
                "color": color,
                "level_percent": normalize_int(level),
                "part_number": normalize_string(part_number),
                "consumable_serial_number": normalize_string(serial_number),
                "status_value": None,
            }
        )

    if device.get("waste_toner_status") is not None:
        rows.append(
            {
                "run_id": run_id,
                "reading_at": reading_at,
                "device_id": device["device_id"],
                "serial_number": device["serial_number"],
                "equipment_id": device["equipment_id"],
                "group_id": group.get("group_id") or "",
                "customer_id": device["customer_id"] or group.get("customer_id") or "",
                "customer_name": device["customer_name"] or group.get("customer_name") or "",
                "consumable_type": "waste_toner",
                "color": "waste",
                "level_percent": None,
                "part_number": None,
                "consumable_serial_number": None,
                "status_value": normalize_int(device["waste_toner_status"]),
            }
        )
    return rows


def build_status_row(
    run_id: str,
    reading_at: str,
    group: dict[str, Any],
    device: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "reading_at": reading_at,
        "device_id": device["device_id"],
        "serial_number": device["serial_number"],
        "group_id": group.get("group_id") or "",
        "management_status": device.get("management_status"),
        "device_status": device.get("device_status"),
        "last_update_raw": device.get("last_update_raw"),
    }


def db_connect(database_url: str):
    try:
        import psycopg
    except Exception as exc:  # pragma: no cover - runtime dependency only
        raise KfsError(
            "PostgreSQL writes require psycopg. Install 'psycopg[binary]' on the Ubuntu host."
        ) from exc
    return psycopg.connect(database_url)


def insert_run(conn, run_row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_runs (
                id, started_at, ended_at, status, source, group_count, device_count, error_count, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_row["id"],
                run_row["started_at"],
                run_row["ended_at"],
                run_row["status"],
                run_row["source"],
                run_row["group_count"],
                run_row["device_count"],
                run_row["error_count"],
                run_row["notes"],
            ),
        )


def update_run(conn, run_row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE kfs_runs
            SET ended_at = %s,
                status = %s,
                group_count = %s,
                device_count = %s,
                error_count = %s,
                notes = %s
            WHERE id = %s
            """,
            (
                run_row["ended_at"],
                run_row["status"],
                run_row["group_count"],
                run_row["device_count"],
                run_row["error_count"],
                run_row["notes"],
                run_row["id"],
            ),
        )


def insert_raw_response(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_raw_responses (
                id, run_id, endpoint, group_id, http_status, kfs_status_code, kfs_message, response_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                row["id"],
                row["run_id"],
                row["endpoint"],
                row["group_id"],
                row["http_status"],
                row["kfs_status_code"],
                row["kfs_message"],
                json.dumps(row["response_json"], ensure_ascii=False),
                row["created_at"],
            ),
        )


def upsert_group(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_groups (
                group_id, parent_group_id, group_name, group_type, registration_id,
                customer_id, customer_name, total_device_count, managed_device_count,
                last_seen_run_id, last_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (group_id) DO UPDATE SET
                parent_group_id = EXCLUDED.parent_group_id,
                group_name = EXCLUDED.group_name,
                group_type = EXCLUDED.group_type,
                registration_id = EXCLUDED.registration_id,
                customer_id = EXCLUDED.customer_id,
                customer_name = EXCLUDED.customer_name,
                total_device_count = EXCLUDED.total_device_count,
                managed_device_count = EXCLUDED.managed_device_count,
                last_seen_run_id = EXCLUDED.last_seen_run_id,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            (
                row["group_id"],
                row.get("parent_group_id"),
                row.get("group_name"),
                row.get("group_type"),
                row.get("registration_id"),
                row.get("customer_id"),
                row.get("customer_name"),
                row.get("total_device_count"),
                row.get("managed_device_count"),
                row["last_seen_run_id"],
                row["last_seen_at"],
            ),
        )


def upsert_device(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_devices (
                device_id, group_id, serial_number, equipment_id, asset_number,
                manufacturer, model_name, hostname, ip_address, mac_address,
                location, customer_id, customer_name, management_status,
                device_status, last_update_raw, last_seen_run_id, last_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::inet, %s,
                      %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (device_id) DO UPDATE SET
                group_id = EXCLUDED.group_id,
                serial_number = EXCLUDED.serial_number,
                equipment_id = EXCLUDED.equipment_id,
                asset_number = EXCLUDED.asset_number,
                manufacturer = EXCLUDED.manufacturer,
                model_name = EXCLUDED.model_name,
                hostname = EXCLUDED.hostname,
                ip_address = EXCLUDED.ip_address,
                mac_address = EXCLUDED.mac_address,
                location = EXCLUDED.location,
                customer_id = EXCLUDED.customer_id,
                customer_name = EXCLUDED.customer_name,
                management_status = EXCLUDED.management_status,
                device_status = EXCLUDED.device_status,
                last_update_raw = EXCLUDED.last_update_raw,
                last_seen_run_id = EXCLUDED.last_seen_run_id,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            (
                row["device_id"],
                row["group_id"],
                row.get("serial_number"),
                row.get("equipment_id"),
                row.get("asset_number"),
                row.get("manufacturer"),
                row.get("model_name"),
                row.get("hostname"),
                row.get("ip_address") or None,
                row.get("mac_address"),
                row.get("location"),
                row.get("customer_id"),
                row.get("customer_name"),
                row.get("management_status"),
                row.get("device_status"),
                row.get("last_update_raw"),
                row["last_seen_run_id"],
                row["last_seen_at"],
            ),
        )


def insert_meter_reading(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_meter_readings (
                id, run_id, reading_at, device_id, serial_number, equipment_id,
                group_id, customer_id, customer_name, counter_name, counter_value, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, device_id, counter_name) DO NOTHING
            """,
            (
                row["id"],
                row["run_id"],
                row["reading_at"],
                row["device_id"],
                row["serial_number"],
                row["equipment_id"],
                row["group_id"],
                row["customer_id"],
                row["customer_name"],
                row["counter_name"],
                row["counter_value"],
                row["created_at"],
            ),
        )


def insert_consumable_reading(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_consumable_readings (
                id, run_id, reading_at, device_id, serial_number, equipment_id,
                group_id, customer_id, customer_name, consumable_type, color,
                level_percent, part_number, consumable_serial_number, status_value, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["id"],
                row["run_id"],
                row["reading_at"],
                row["device_id"],
                row["serial_number"],
                row["equipment_id"],
                row["group_id"],
                row["customer_id"],
                row["customer_name"],
                row["consumable_type"],
                row["color"],
                row["level_percent"],
                row["part_number"],
                row["consumable_serial_number"],
                row["status_value"],
                row["created_at"],
            ),
        )


def insert_status_reading(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_device_status_readings (
                id, run_id, reading_at, device_id, serial_number, group_id,
                management_status, device_status, last_update_raw, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["id"],
                row["run_id"],
                row["reading_at"],
                row["device_id"],
                row["serial_number"],
                row["group_id"],
                row["management_status"],
                row["device_status"],
                row["last_update_raw"],
                row["created_at"],
            ),
        )


def insert_device_log_reading(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_device_log_readings (
                id, run_id, reading_at, device_id, serial_number, group_id,
                log_type, log_detail, log_description, log_counter,
                event_started_at, event_ended_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["id"],
                row["run_id"],
                row["reading_at"],
                row["device_id"],
                row["serial_number"],
                row["group_id"],
                row["log_type"],
                row["log_detail"],
                row["log_description"],
                row["log_counter"],
                row["event_started_at"],
                row["event_ended_at"],
                row["created_at"],
            ),
        )


def insert_device_run_delta(conn, row: dict[str, Any]) -> None:
    columns = [
        "id",
        "run_id",
        "previous_run_id",
        "device_id",
        "serial_number",
        "group_id",
        "customer_id",
        "customer_name",
        "current_reading_at",
        "previous_reading_at",
        "total_meter_current",
        "total_meter_previous",
        "total_meter_delta",
        "black_white_meter_current",
        "black_white_meter_previous",
        "black_white_meter_delta",
        "color_meter_current",
        "color_meter_previous",
        "color_meter_delta",
        "full_color_meter_current",
        "full_color_meter_previous",
        "full_color_meter_delta",
        "copier_total_current",
        "copier_total_previous",
        "copier_total_delta",
        "copier_bw_current",
        "copier_bw_previous",
        "copier_bw_delta",
        "copier_color_total_current",
        "copier_color_total_previous",
        "copier_color_total_delta",
        "printer_total_current",
        "printer_total_previous",
        "printer_total_delta",
        "printer_bw_current",
        "printer_bw_previous",
        "printer_bw_delta",
        "printer_color_total_current",
        "printer_color_total_previous",
        "printer_color_total_delta",
        "scan_total_current",
        "scan_total_previous",
        "scan_total_delta",
        "fax_total_current",
        "fax_total_previous",
        "fax_total_delta",
        "life_count_total_current",
        "life_count_total_previous",
        "life_count_total_delta",
        "black_toner_level_current",
        "black_toner_level_previous",
        "black_toner_level_delta",
        "cyan_toner_level_current",
        "cyan_toner_level_previous",
        "cyan_toner_level_delta",
        "magenta_toner_level_current",
        "magenta_toner_level_previous",
        "magenta_toner_level_delta",
        "yellow_toner_level_current",
        "yellow_toner_level_previous",
        "yellow_toner_level_delta",
        "waste_toner_status_current",
        "waste_toner_status_previous",
        "waste_toner_status_delta",
        "management_status_current",
        "management_status_previous",
        "management_status_delta",
        "device_status_current",
        "device_status_previous",
        "device_status_delta",
        "last_update_raw_current",
        "last_update_raw_previous",
        "last_update_raw_delta",
        "notes",
        "created_at",
    ]
    values = {key: row.get(key) for key in columns}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_device_run_deltas (
                id, run_id, previous_run_id, device_id, serial_number, group_id, customer_id, customer_name,
                current_reading_at, previous_reading_at,
                total_meter_current, total_meter_previous, total_meter_delta,
                black_white_meter_current, black_white_meter_previous, black_white_meter_delta,
                color_meter_current, color_meter_previous, color_meter_delta,
                full_color_meter_current, full_color_meter_previous, full_color_meter_delta,
                copier_total_current, copier_total_previous, copier_total_delta,
                copier_bw_current, copier_bw_previous, copier_bw_delta,
                copier_color_total_current, copier_color_total_previous, copier_color_total_delta,
                printer_total_current, printer_total_previous, printer_total_delta,
                printer_bw_current, printer_bw_previous, printer_bw_delta,
                printer_color_total_current, printer_color_total_previous, printer_color_total_delta,
                scan_total_current, scan_total_previous, scan_total_delta,
                fax_total_current, fax_total_previous, fax_total_delta,
                life_count_total_current, life_count_total_previous, life_count_total_delta,
                black_toner_level_current, black_toner_level_previous, black_toner_level_delta,
                cyan_toner_level_current, cyan_toner_level_previous, cyan_toner_level_delta,
                magenta_toner_level_current, magenta_toner_level_previous, magenta_toner_level_delta,
                yellow_toner_level_current, yellow_toner_level_previous, yellow_toner_level_delta,
                waste_toner_status_current, waste_toner_status_previous, waste_toner_status_delta,
                management_status_current, management_status_previous, management_status_delta,
                device_status_current, device_status_previous, device_status_delta,
                last_update_raw_current, last_update_raw_previous, last_update_raw_delta,
                notes, created_at
            ) VALUES (
                %(id)s, %(run_id)s, %(previous_run_id)s, %(device_id)s, %(serial_number)s, %(group_id)s, %(customer_id)s, %(customer_name)s,
                %(current_reading_at)s, %(previous_reading_at)s,
                %(total_meter_current)s, %(total_meter_previous)s, %(total_meter_delta)s,
                %(black_white_meter_current)s, %(black_white_meter_previous)s, %(black_white_meter_delta)s,
                %(color_meter_current)s, %(color_meter_previous)s, %(color_meter_delta)s,
                %(full_color_meter_current)s, %(full_color_meter_previous)s, %(full_color_meter_delta)s,
                %(copier_total_current)s, %(copier_total_previous)s, %(copier_total_delta)s,
                %(copier_bw_current)s, %(copier_bw_previous)s, %(copier_bw_delta)s,
                %(copier_color_total_current)s, %(copier_color_total_previous)s, %(copier_color_total_delta)s,
                %(printer_total_current)s, %(printer_total_previous)s, %(printer_total_delta)s,
                %(printer_bw_current)s, %(printer_bw_previous)s, %(printer_bw_delta)s,
                %(printer_color_total_current)s, %(printer_color_total_previous)s, %(printer_color_total_delta)s,
                %(scan_total_current)s, %(scan_total_previous)s, %(scan_total_delta)s,
                %(fax_total_current)s, %(fax_total_previous)s, %(fax_total_delta)s,
                %(life_count_total_current)s, %(life_count_total_previous)s, %(life_count_total_delta)s,
                %(black_toner_level_current)s, %(black_toner_level_previous)s, %(black_toner_level_delta)s,
                %(cyan_toner_level_current)s, %(cyan_toner_level_previous)s, %(cyan_toner_level_delta)s,
                %(magenta_toner_level_current)s, %(magenta_toner_level_previous)s, %(magenta_toner_level_delta)s,
                %(yellow_toner_level_current)s, %(yellow_toner_level_previous)s, %(yellow_toner_level_delta)s,
                %(waste_toner_status_current)s, %(waste_toner_status_previous)s, %(waste_toner_status_delta)s,
                %(management_status_current)s, %(management_status_previous)s, %(management_status_delta)s,
                %(device_status_current)s, %(device_status_previous)s, %(device_status_delta)s,
                %(last_update_raw_current)s, %(last_update_raw_previous)s, %(last_update_raw_delta)s,
                %(notes)s, %(created_at)s
            )
            ON CONFLICT (run_id, device_id) DO NOTHING
            """,
            values,
        )


def build_device_current_snapshot(device: dict[str, Any]) -> dict[str, Any]:
    counters = device.get("counters") or device.get("counter") or {}

    def counter_value(field: str) -> int | None:
        for alias in COUNTER_FIELD_ALIASES.get(field.lower(), [field]):
            value = get_first_non_empty(counters, alias)
            if value is not None:
                return normalize_int(value)
        return None

    return {
        "total_meter": counter_value("total"),
        "black_white_meter": counter_value("blackWhite"),
        "color_meter": counter_value("color"),
        "full_color_meter": counter_value("fullColor"),
        "copier_total": counter_value("copierTotal"),
        "copier_bw": counter_value("copierBw"),
        "copier_color_total": counter_value("copierColorTotal"),
        "printer_total": counter_value("printerTotal"),
        "printer_bw": counter_value("printerBw"),
        "printer_color_total": counter_value("printerColorTotal"),
        "scan_total": counter_value("scanTotal"),
        "fax_total": counter_value("faxTotal"),
        "life_count_total": counter_value("lifecountTotal"),
        "black_toner_level": normalize_int(device.get("black_toner_level")),
        "cyan_toner_level": normalize_int(device.get("cyan_toner_level")),
        "magenta_toner_level": normalize_int(device.get("magenta_toner_level")),
        "yellow_toner_level": normalize_int(device.get("yellow_toner_level")),
        "waste_toner_status": normalize_int(device.get("waste_toner_status")),
        "management_status": normalize_int(device.get("management_status")),
        "device_status": normalize_int(device.get("device_status")),
        "last_update_raw": normalize_raw_bigint(device.get("last_update_raw")),
    }


def delta_value(current: Any, previous: Any) -> int | None:
    current_int = normalize_int(current)
    previous_int = normalize_int(previous)
    if current_int is None or previous_int is None:
        return None
    return current_int - previous_int


def fetch_previous_device_snapshot(conn, device_id: str, current_started_at: datetime) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH prev_run AS (
                SELECT r.id, r.started_at
                FROM kfs_device_status_readings s
                JOIN kfs_runs r ON r.id = s.run_id
                WHERE s.device_id = %s
                  AND r.started_at < %s
                ORDER BY r.started_at DESC, r.ended_at DESC
                LIMIT 1
            ),
            meter AS (
                SELECT
                    MAX(mr.reading_at) AS previous_meter_reading_at,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'total') AS previous_total_meter,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'blackWhite') AS previous_black_white_meter,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'color') AS previous_color_meter,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'fullColor') AS previous_full_color_meter,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'copierTotal') AS previous_copier_total,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'copierBw') AS previous_copier_bw,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'copierColorTotal') AS previous_copier_color_total,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'printerTotal') AS previous_printer_total,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'printerBw') AS previous_printer_bw,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'printerColorTotal') AS previous_printer_color_total,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'scanTotal') AS previous_scan_total,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'faxTotal') AS previous_fax_total,
                    MAX(mr.counter_value) FILTER (WHERE mr.counter_name = 'lifecountTotal') AS previous_life_count_total
                FROM kfs_meter_readings mr
                JOIN prev_run pr ON pr.id = mr.run_id
                WHERE mr.device_id = %s
            ),
            consumable AS (
                SELECT
                    MAX(cr.reading_at) AS previous_consumable_reading_at,
                    MAX(cr.level_percent) FILTER (WHERE cr.consumable_type = 'toner' AND cr.color = 'black') AS previous_black_toner_level,
                    MAX(cr.level_percent) FILTER (WHERE cr.consumable_type = 'toner' AND cr.color = 'cyan') AS previous_cyan_toner_level,
                    MAX(cr.level_percent) FILTER (WHERE cr.consumable_type = 'toner' AND cr.color = 'magenta') AS previous_magenta_toner_level,
                    MAX(cr.level_percent) FILTER (WHERE cr.consumable_type = 'toner' AND cr.color = 'yellow') AS previous_yellow_toner_level,
                    MAX(cr.status_value) FILTER (WHERE cr.consumable_type = 'waste_toner') AS previous_waste_toner_status
                FROM kfs_consumable_readings cr
                JOIN prev_run pr ON pr.id = cr.run_id
                WHERE cr.device_id = %s
            ),
            status AS (
                SELECT
                    MAX(sr.reading_at) AS previous_status_reading_at,
                    MAX(sr.management_status) AS previous_management_status,
                    MAX(sr.device_status) AS previous_device_status,
                    MAX(sr.last_update_raw) AS previous_last_update_raw
                FROM kfs_device_status_readings sr
                JOIN prev_run pr ON pr.id = sr.run_id
                WHERE sr.device_id = %s
            )
            SELECT
                pr.id AS previous_run_id,
                pr.started_at AS previous_run_started_at,
                meter.previous_meter_reading_at,
                meter.previous_total_meter,
                meter.previous_black_white_meter,
                meter.previous_color_meter,
                meter.previous_full_color_meter,
                meter.previous_copier_total,
                meter.previous_copier_bw,
                meter.previous_copier_color_total,
                meter.previous_printer_total,
                meter.previous_printer_bw,
                meter.previous_printer_color_total,
                meter.previous_scan_total,
                meter.previous_fax_total,
                meter.previous_life_count_total,
                consumable.previous_consumable_reading_at,
                consumable.previous_black_toner_level,
                consumable.previous_cyan_toner_level,
                consumable.previous_magenta_toner_level,
                consumable.previous_yellow_toner_level,
                consumable.previous_waste_toner_status,
                status.previous_status_reading_at,
                status.previous_management_status,
                status.previous_device_status,
                status.previous_last_update_raw
            FROM (SELECT 1) seed
            LEFT JOIN prev_run pr ON true
            LEFT JOIN meter ON true
            LEFT JOIN consumable ON true
            LEFT JOIN status ON true
            """,
            (device_id, current_started_at, device_id, device_id, device_id),
        )
        row = cur.fetchone()
        if not row:
            return {}
        columns = [
            "previous_run_id",
            "previous_run_started_at",
            "previous_meter_reading_at",
            "previous_total_meter",
            "previous_black_white_meter",
            "previous_color_meter",
            "previous_full_color_meter",
            "previous_copier_total",
            "previous_copier_bw",
            "previous_copier_color_total",
            "previous_printer_total",
            "previous_printer_bw",
            "previous_printer_color_total",
            "previous_scan_total",
            "previous_fax_total",
            "previous_life_count_total",
            "previous_consumable_reading_at",
            "previous_black_toner_level",
            "previous_cyan_toner_level",
            "previous_magenta_toner_level",
            "previous_yellow_toner_level",
            "previous_waste_toner_status",
            "previous_status_reading_at",
            "previous_management_status",
            "previous_device_status",
            "previous_last_update_raw",
        ]
        return dict(zip(columns, row, strict=False))


def build_device_run_delta_row(
    run_row: dict[str, Any],
    current_reading_at: str,
    group: dict[str, Any],
    device: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    current = build_device_current_snapshot(device)
    previous = previous or {}
    notes: list[str] = []
    if not previous.get("previous_run_id"):
        notes.append("first-seen device")

    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "run_id": run_row["id"],
        "previous_run_id": previous.get("previous_run_id"),
        "device_id": device["device_id"],
        "serial_number": device.get("serial_number"),
        "group_id": group.get("group_id") or device.get("group_id"),
        "customer_id": device.get("customer_id") or group.get("customer_id"),
        "customer_name": device.get("customer_name") or group.get("customer_name"),
        "current_reading_at": current_reading_at,
        "previous_reading_at": previous.get("previous_status_reading_at")
        or previous.get("previous_meter_reading_at")
        or previous.get("previous_consumable_reading_at"),
        "notes": "",
        "created_at": utc_now().astimezone(timezone.utc),
    }

    for field in RUN_DELTA_COUNTER_FIELDS:
        current_value = current.get(field)
        previous_value = previous.get(f"previous_{field}")
        row[f"{field}_current"] = current_value
        row[f"{field}_previous"] = previous_value
        row[f"{field}_delta"] = delta_value(current_value, previous_value)
        if row[f"{field}_delta"] is not None and row[f"{field}_delta"] < 0:
            notes.append(f"{field} decreased")

    for field in RUN_DELTA_CONSUMABLE_FIELDS:
        current_value = current.get(field)
        previous_value = previous.get(f"previous_{field}")
        row[f"{field}_current"] = current_value
        row[f"{field}_previous"] = previous_value
        row[f"{field}_delta"] = delta_value(current_value, previous_value)
        if row[f"{field}_delta"] is not None and row[f"{field}_delta"] > 0:
            notes.append(f"{field} increased")

    for field in RUN_DELTA_STATUS_FIELDS:
        current_value = current.get(field)
        previous_value = previous.get(f"previous_{field}")
        row[f"{field}_current"] = current_value
        row[f"{field}_previous"] = previous_value
        row[f"{field}_delta"] = delta_value(current_value, previous_value)

    row["notes"] = "; ".join(notes)
    return row


def insert_mapping_stub(conn, row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kfs_autotask_mapping (
                id, kfs_device_id, autotask_company_id, autotask_asset_id,
                autotask_configuration_item_id, autotask_device_name, notes,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (kfs_device_id) DO UPDATE SET
                autotask_company_id = EXCLUDED.autotask_company_id,
                autotask_asset_id = EXCLUDED.autotask_asset_id,
                autotask_configuration_item_id = EXCLUDED.autotask_configuration_item_id,
                autotask_device_name = EXCLUDED.autotask_device_name,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
            """,
            (
                row["id"],
                row["kfs_device_id"],
                row.get("autotask_company_id"),
                row.get("autotask_asset_id"),
                row.get("autotask_configuration_item_id"),
                row.get("autotask_device_name"),
                row.get("notes"),
                row["created_at"],
                row["updated_at"],
            ),
        )


def make_run_row(source: str) -> dict[str, Any]:
    now = utc_now().astimezone(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "started_at": now,
        "ended_at": now,
        "status": "running",
        "source": source,
        "group_count": 0,
        "device_count": 0,
        "error_count": 0,
        "notes": "",
    }


def write_summary(writer: ArtifactWriter, run_row: dict[str, Any], stats: dict[str, Any]) -> None:
    payload = {
        "run": {
            "id": run_row["id"],
            "started_at": run_row["started_at"].isoformat(),
            "ended_at": run_row["ended_at"].isoformat(),
            "status": run_row["status"],
            "source": run_row["source"],
        },
        "stats": stats,
    }
    writer.write_json(Path("summary.json"), payload)
    writer.write_json(Path("manifest.json"), payload)


def select_secrets_text(config: KfsConfig) -> list[str]:
    values = [
        config.auth_token,
        config.username,
        config.password,
        config.request_from,
        config.request_to,
    ]
    return [value for value in values if value]


def require_login_inputs(config: KfsConfig) -> None:
    missing = []
    if not normalize_string(config.auth_token) and not (
        normalize_string(config.access_id) and normalize_string(config.access_password)
    ):
        missing.append("auth token")
    if not normalize_string(config.username):
        missing.append("username")
    if not normalize_string(config.password):
        missing.append("password")
    if missing:
        raise KfsError(
            "Missing KFS inputs: "
            + ", ".join(missing)
            + ". Provide them via OpenClaw secure config, env vars, or CLI flags."
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenClaw KFS collector")
    parser.add_argument("--config", help="Path to OpenClaw secure JSON config")
    parser.add_argument("--secrets-path", help="Explicit secure JSON path override")
    parser.add_argument("--output-root", help="Run output root directory")
    parser.add_argument("--base-url", help="KFS base URL")
    parser.add_argument("--request-from", help="KFS RequestFrom")
    parser.add_argument("--request-to", help="KFS RequestTo")
    parser.add_argument("--auth-token", help="Raw Basic auth token without the 'Basic ' prefix")
    parser.add_argument("--access-id", help="KFS access ID for building the Basic header")
    parser.add_argument("--access-password", help="KFS access password for building the Basic header")
    parser.add_argument("--username", help="KFS API username")
    parser.add_argument("--password", help="KFS API password")
    parser.add_argument("--database-url", help="PostgreSQL connection string")
    parser.add_argument("--source", help="Source string stored in kfs_runs")
    parser.add_argument("--timeout-sec", type=int, help="HTTP timeout in seconds")
    parser.add_argument("--scope", type=int, help="DeviceList scope value")
    parser.add_argument("--dry-run", action="store_true", help="Skip PostgreSQL writes")
    args = parser.parse_args(argv)

    config = load_config(args)
    config.secrets_path = config.secrets_path.expanduser()
    config.output_root = config.output_root.expanduser()
    config.request_to = config.request_to or DEFAULT_REQUEST_TO
    config.base_url = config.base_url.rstrip("/")

    require_login_inputs(config)

    run_stamp = utc_now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = config.output_root / run_stamp
    writer = ArtifactWriter(run_root)
    writer.write_json(
        Path("run-config.json"),
        {
            "base_url": config.base_url,
            "request_from": config.request_from,
            "request_to": config.request_to,
            "source": config.source,
            "timeout_sec": config.timeout_sec,
            "scope": config.scope,
            "dry_run": config.dry_run,
            "secrets_path": str(config.secrets_path),
        },
    )

    run_row = make_run_row(config.source)
    stats = {
        "groups": 0,
        "devices": 0,
        "raw_responses": 0,
        "meter_readings": 0,
        "consumable_readings": 0,
        "status_readings": 0,
        "device_log_readings": 0,
        "run_deltas": 0,
        "errors": 0,
    }
    group_rows: list[dict[str, Any]] = []
    device_rows: list[dict[str, Any]] = []
    notes: list[str] = []
    login_response: dict[str, Any] | None = None
    seen_log_keys: set[str] = set()

    writer.log("Starting KFS collector")
    writer.log(f"Run root: {run_root}")
    writer.log(f"Secure config path: {config.secrets_path}")

    client = KfsHttpClient(config, writer)
    db_conn = None

    try:
        if not config.dry_run:
            if not normalize_string(config.database_url):
                raise KfsError("DATABASE_URL is required unless --dry-run is used.")
            db_conn = db_connect(config.database_url)
            insert_run(db_conn, run_row)
            db_conn.commit()

        login_body = make_request_body(
            config.request_from,
            config.request_to,
            "Global_KFS_Pull_Login",
            {
                "id": config.username,
                "password": config.password,
                "isPersistent": False,
                "timeZone": -400,
            },
        )
        login_response = client.request("POST", "/KFS/Login", login_body)
        client.log_request("login", login_body, login_response)
        stats["raw_responses"] += 1
        if db_conn is not None:
            insert_raw_response(
                db_conn,
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_row["id"],
                    "endpoint": "/KFS/Login",
                    "group_id": None,
                    "http_status": login_response["status"],
                    "kfs_status_code": login_response["body_status_code"],
                    "kfs_message": login_response["body_status_message"],
                    "response_json": login_response["body_for_storage"],
                    "created_at": utc_now().astimezone(timezone.utc),
                },
            )
            db_conn.commit()

        login_code = login_response["body_status_code"] or login_response["status"]
        if login_code == 401:
            raise KfsAuthError("KFS login returned 401; stopping immediately without retrying.")
        if login_code != 200:
            message = login_response["body_status_message"] or f"HTTP {login_response['status']}"
            raise KfsAuthError(f"KFS login failed with status {login_code}: {message}")

        writer.log("Login completed")
        if login_response["headers"].get("set-cookie") or login_response["headers"].get("Set-Cookie"):
            writer.log("Login returned a session cookie")
        else:
            writer.log("Login did not expose a set-cookie header; relying on cookie jar")

        group_body = make_request_body(
            config.request_from,
            config.request_to,
            "Global_KFS_Pull_GroupList",
            {"groupAttrIds": GROUP_ATTR_IDS},
        )
        group_response = client.request("POST", "/KFS/GroupList", group_body)
        client.log_request("group-list", group_body, group_response)
        stats["raw_responses"] += 1
        if db_conn is not None:
            insert_raw_response(
                db_conn,
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_row["id"],
                    "endpoint": "/KFS/GroupList",
                    "group_id": None,
                    "http_status": group_response["status"],
                    "kfs_status_code": group_response["body_status_code"],
                    "kfs_message": group_response["body_status_message"],
                    "response_json": group_response["body_for_storage"],
                    "created_at": utc_now().astimezone(timezone.utc),
                },
            )
            db_conn.commit()

        group_code = group_response["body_status_code"] or group_response["status"]
        if group_code != 200:
            message = group_response["body_status_message"] or f"HTTP {group_response['status']}"
            raise KfsError(f"GroupList failed with status {group_code}: {message}")

        group_rows = extract_group_rows(group_response["parsed"])
        stats["groups"] = len(group_rows)
        if not group_rows:
            raise KfsError("GroupList returned no usable groups.")

        seen_devices: set[str] = set()
        reading_at = utc_now().astimezone(timezone.utc).isoformat()

        for group in group_rows:
            group_id = group.get("group_id")
            if not group_id:
                notes.append(f"Skipped one group without groupId: {group.get('group_name') or '<unnamed>'}")
                stats["errors"] += 1
                continue
            if db_conn is not None:
                upsert_group(
                    db_conn,
                    {
                        **group,
                        "last_seen_run_id": run_row["id"],
                        "last_seen_at": utc_now().astimezone(timezone.utc),
                    },
                )
                db_conn.commit()

            device_body = make_request_body(
                config.request_from,
                config.request_to,
                "Global_KFS_Pull_DeviceList",
                {
                    "groupId": group_id,
                    "scope": config.scope,
                    "deviceAttrIds": DEVICE_ATTR_IDS,
                    "counters": COUNTER_ATTR_IDS,
                },
            )
            try:
                device_response = client.request("POST", "/KFS/DeviceList", device_body, group_id=group_id)
            except TimeoutError as exc:
                notes.append(f"DeviceList timed out for group {group_id}: {exc}")
                stats["errors"] += 1
                continue
            client.log_request(f"device-list-{slugify(group_id)}", device_body, device_response)
            stats["raw_responses"] += 1
            if db_conn is not None:
                insert_raw_response(
                    db_conn,
                    {
                        "id": str(uuid.uuid4()),
                        "run_id": run_row["id"],
                        "endpoint": "/KFS/DeviceList",
                        "group_id": group_id,
                        "http_status": device_response["status"],
                        "kfs_status_code": device_response["body_status_code"],
                        "kfs_message": device_response["body_status_message"],
                        "response_json": device_response["body_for_storage"],
                        "created_at": utc_now().astimezone(timezone.utc),
                    },
                )
                db_conn.commit()
            device_code = device_response["body_status_code"] or device_response["status"]
            if device_code != 200:
                message = device_response["body_status_message"] or f"HTTP {device_response['status']}"
                notes.append(f"DeviceList failed for group {group_id}: {message}")
                stats["errors"] += 1
                continue

            devices = extract_device_rows(device_response["parsed"])
            for device in devices:
                device["group_id"] = group_id
                if device["device_id"] in seen_devices:
                    continue
                seen_devices.add(device["device_id"])
                device_rows.append(device)

            log_body = make_request_body(
                config.request_from,
                config.request_to,
                "Global_KFS_Pull_DeviceLogList",
                {
                    "groupId": group_id,
                    "scope": config.scope,
                },
            )
            try:
                log_response = client.request("POST", "/KFS/DeviceLogList", log_body, group_id=group_id)
            except TimeoutError as exc:
                notes.append(f"DeviceLogList timed out for group {group_id}: {exc}")
                stats["errors"] += 1
                continue
            client.log_request(f"device-log-list-{slugify(group_id)}", log_body, log_response)
            stats["raw_responses"] += 1
            if db_conn is not None:
                insert_raw_response(
                    db_conn,
                    {
                        "id": str(uuid.uuid4()),
                        "run_id": run_row["id"],
                        "endpoint": "/KFS/DeviceLogList",
                        "group_id": group_id,
                        "http_status": log_response["status"],
                        "kfs_status_code": log_response["body_status_code"],
                        "kfs_message": log_response["body_status_message"],
                        "response_json": log_response["body_for_storage"],
                        "created_at": utc_now().astimezone(timezone.utc),
                    },
                )
                db_conn.commit()
            log_code = log_response["body_status_code"] or log_response["status"]
            if log_code != 200:
                message = log_response["body_status_message"] or f"HTTP {log_response['status']}"
                notes.append(f"DeviceLogList failed for group {group_id}: {message}")
                stats["errors"] += 1
                continue

            device_log_rows = extract_device_log_rows(log_response["parsed"])
            for log_row in device_log_rows:
                log_row["group_id"] = log_row["group_id"] or group_id
                if not log_row["device_id"]:
                    continue
                log_key = "|".join(
                    [
                        log_row["device_id"],
                        str(log_row.get("group_id") or ""),
                        str(log_row.get("log_type") or ""),
                        str(log_row.get("log_detail") or ""),
                        str(log_row.get("log_description") or ""),
                        str(log_row.get("log_counter") or ""),
                        str(log_row.get("event_started_at") or ""),
                        str(log_row.get("event_ended_at") or ""),
                    ]
                )
                if log_key in seen_log_keys:
                    continue
                seen_log_keys.add(log_key)
                if db_conn is not None:
                    log_row["id"] = str(uuid.uuid4())
                    log_row["run_id"] = run_row["id"]
                    log_row["reading_at"] = reading_at
                    log_row["created_at"] = utc_now().astimezone(timezone.utc)
                    insert_device_log_reading(db_conn, log_row)
                stats["device_log_readings"] += 1

        stats["devices"] = len(device_rows)
        if db_conn is not None:
            for group in group_rows:
                if not group.get("group_id"):
                    continue
                upsert_group(
                    db_conn,
                    {
                        **group,
                        "last_seen_run_id": run_row["id"],
                        "last_seen_at": utc_now().astimezone(timezone.utc),
                    },
                )
            db_conn.commit()

            for device in device_rows:
                group = next((item for item in group_rows if item.get("group_id") == device["group_id"]), {})
                upsert_device(
                    db_conn,
                    {
                        **device,
                        "last_seen_run_id": run_row["id"],
                        "last_seen_at": utc_now().astimezone(timezone.utc),
                    },
                )
                db_conn.commit()

                status_row = build_status_row(run_row["id"], reading_at, group, device)
                status_row["id"] = str(uuid.uuid4())
                status_row["created_at"] = utc_now().astimezone(timezone.utc)
                insert_status_reading(db_conn, status_row)
                stats["status_readings"] += 1

                for counter_row in build_counter_rows(run_row["id"], reading_at, group, device):
                    counter_row["id"] = str(uuid.uuid4())
                    counter_row["created_at"] = utc_now().astimezone(timezone.utc)
                    insert_meter_reading(db_conn, counter_row)
                    stats["meter_readings"] += 1

                for consumable_row in build_consumable_rows(run_row["id"], reading_at, group, device):
                    consumable_row["id"] = str(uuid.uuid4())
                    consumable_row["created_at"] = utc_now().astimezone(timezone.utc)
                    insert_consumable_reading(db_conn, consumable_row)
                    stats["consumable_readings"] += 1

                previous_snapshot = fetch_previous_device_snapshot(
                    db_conn,
                    device["device_id"],
                    run_row["started_at"],
                )
                delta_row = build_device_run_delta_row(
                    run_row,
                    reading_at,
                    group,
                    device,
                    previous_snapshot,
                )
                insert_device_run_delta(db_conn, delta_row)
                stats["run_deltas"] += 1

        run_row["status"] = "ok"
        run_row["ended_at"] = utc_now().astimezone(timezone.utc)
        run_row["group_count"] = stats["groups"]
        run_row["device_count"] = stats["devices"]
        run_row["error_count"] = stats["errors"]
        run_row["notes"] = "; ".join(notes)
        if db_conn is not None:
            update_run(db_conn, run_row)
            db_conn.commit()
            db_conn.close()

        writer.log("KFS collector completed successfully")
        writer.write_json(
            Path("results.json"),
            {
                "status": "ok",
                "run_id": run_row["id"],
                "group_count": stats["groups"],
                "device_count": stats["devices"],
                "meter_readings": stats["meter_readings"],
                "consumable_readings": stats["consumable_readings"],
                "status_readings": stats["status_readings"],
                "device_log_readings": stats["device_log_readings"],
                "run_deltas": stats["run_deltas"],
                "error_count": stats["errors"],
                "notes": notes,
            },
        )
        write_summary(writer, run_row, stats)
        return 0
    except KfsAuthError as exc:
        run_row["status"] = "failed"
        run_row["ended_at"] = utc_now().astimezone(timezone.utc)
        run_row["error_count"] = max(run_row["error_count"], 1)
        run_row["notes"] = str(exc)
        writer.log(mask_text(f"AUTH ERROR: {exc}", select_secrets_text(config)))
        writer.write_json(
            Path("results.json"),
            {
                "status": "failed",
                "error": str(exc),
                "run_id": run_row["id"],
                "run_deltas": stats["run_deltas"],
            },
        )
        if db_conn is not None:
            update_run(db_conn, run_row)
            db_conn.commit()
            db_conn.close()
        write_summary(writer, run_row, stats)
        return 2
    except Exception as exc:
        run_row["status"] = "failed"
        run_row["ended_at"] = utc_now().astimezone(timezone.utc)
        run_row["error_count"] = max(run_row["error_count"], 1)
        run_row["notes"] = f"{type(exc).__name__}: {exc}"
        writer.log(mask_text(f"ERROR: {type(exc).__name__}: {exc}", select_secrets_text(config)))
        writer.log(traceback.format_exc())
        writer.write_json(
            Path("results.json"),
            {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "run_id": run_row["id"],
                "run_deltas": stats["run_deltas"],
            },
        )
        if db_conn is not None:
            update_run(db_conn, run_row)
            db_conn.commit()
            db_conn.close()
        write_summary(writer, run_row, stats)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
