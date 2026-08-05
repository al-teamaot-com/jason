from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Mapping, Protocol, Sequence
from urllib import error, request


EXIT_USAGE = 2
EXIT_UNAVAILABLE = 10
EXIT_UNAUTHORIZED = 11
EXIT_NOT_FOUND = 12
EXIT_MALFORMED = 13
EXIT_BACKEND = 14


class SecretProviderError(RuntimeError):
    exit_code = EXIT_BACKEND


class ProviderUnavailableError(SecretProviderError):
    exit_code = EXIT_UNAVAILABLE


class ProviderUnauthorizedError(SecretProviderError):
    exit_code = EXIT_UNAUTHORIZED


class SecretNotFoundError(SecretProviderError):
    exit_code = EXIT_NOT_FOUND


class SecretMalformedError(SecretProviderError):
    exit_code = EXIT_MALFORMED


class SecretBackend(Protocol):
    def resolve(self, provider_path: str, field: str) -> str: ...
    def health(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SecretMapping:
    provider_path: str
    field: str


def load_mappings(path: Path) -> dict[str, SecretMapping]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProviderUnavailableError("Secret mapping file is unavailable.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SecretMalformedError("Secret mapping file is invalid.") from exc

    if not isinstance(raw, dict):
        raise SecretMalformedError("Secret mapping file must contain an object.")

    mappings: dict[str, SecretMapping] = {}
    for logical_name, value in raw.items():
        if not isinstance(logical_name, str) or not logical_name.strip():
            raise SecretMalformedError("Secret mapping contains an invalid logical name.")
        if not isinstance(value, dict):
            raise SecretMalformedError("Secret mapping entry must contain an object.")
        provider_path = value.get("path")
        field = value.get("field")
        if not isinstance(provider_path, str) or not provider_path.strip():
            raise SecretMalformedError("Secret mapping entry is missing a provider path.")
        if not isinstance(field, str) or not field.strip():
            raise SecretMalformedError("Secret mapping entry is missing a field.")
        mappings[logical_name.strip()] = SecretMapping(provider_path.strip(), field.strip())
    return mappings


def resolve_mapping(mappings: Mapping[str, SecretMapping], logical_name: str) -> SecretMapping:
    normalized = logical_name.strip()
    if not normalized:
        raise SecretMalformedError("Logical secret name must be non-empty.")
    try:
        return mappings[normalized]
    except KeyError as exc:
        raise SecretNotFoundError("Logical secret name is not mapped.") from exc


@dataclass(frozen=True, slots=True)
class TestFileBackend:
    values_path: Path

    def _values(self) -> dict[str, dict[str, str]]:
        try:
            raw = json.loads(self.values_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProviderUnavailableError("Test secret values are unavailable.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise SecretMalformedError("Test secret values are invalid.") from exc
        if not isinstance(raw, dict):
            raise SecretMalformedError("Test secret values must contain an object.")
        return raw

    def resolve(self, provider_path: str, field: str) -> str:
        values = self._values()
        record = values.get(provider_path)
        if not isinstance(record, dict) or field not in record:
            raise SecretNotFoundError("Mapped secret value was not found.")
        value = record[field]
        if not isinstance(value, str) or not value:
            raise SecretMalformedError("Mapped secret value is empty or malformed.")
        return value

    def health(self) -> str:
        self._values()
        return "healthy"


@dataclass(frozen=True, slots=True)
class OpenBaoBackend:
    address: str
    token_file: Path
    timeout_seconds: float = 5.0

    def _token(self) -> str:
        try:
            token = self.token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ProviderUnauthorizedError("OpenBao authentication material is unavailable.") from exc
        if not token:
            raise ProviderUnauthorizedError("OpenBao authentication material is empty.")
        return token

    def _request_json(self, url: str, *, authenticated: bool) -> dict:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["X-Vault-Token"] = self._token()
        req = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderUnauthorizedError("OpenBao rejected the configured identity.") from exc
            if exc.code == 404:
                raise SecretNotFoundError("Mapped OpenBao secret was not found.") from exc
            raise ProviderUnavailableError("OpenBao returned an unavailable response.") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError("OpenBao is unavailable.") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SecretMalformedError("OpenBao returned malformed JSON.") from exc
        if not isinstance(parsed, dict):
            raise SecretMalformedError("OpenBao returned an invalid response.")
        return parsed

    def resolve(self, provider_path: str, field: str) -> str:
        normalized_path = provider_path.strip().lstrip("/")
        if not normalized_path:
            raise SecretMalformedError("OpenBao provider path is empty.")
        payload = self._request_json(
            f"{self.address.rstrip('/')}/v1/{normalized_path}", authenticated=True
        )
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        if not isinstance(data, dict) or field not in data:
            raise SecretNotFoundError("Mapped OpenBao field was not found.")
        value = data[field]
        if not isinstance(value, str) or not value:
            raise SecretMalformedError("Mapped OpenBao value is empty or malformed.")
        return value

    def health(self) -> str:
        payload = self._request_json(
            f"{self.address.rstrip('/')}/v1/sys/health", authenticated=False
        )
        if payload.get("sealed") is True:
            raise ProviderUnavailableError("OpenBao is sealed.")
        return "healthy"


def build_backend(environment: Mapping[str, str]) -> SecretBackend:
    backend_name = environment.get("JASON_SECRET_BACKEND", "openbao").strip().lower()
    if backend_name == "test-file":
        values = environment.get("JASON_SECRET_TEST_VALUES_FILE", "").strip()
        if not values:
            raise ProviderUnavailableError("Test backend values file is not configured.")
        return TestFileBackend(Path(values).expanduser())
    if backend_name != "openbao":
        raise ProviderUnavailableError("Configured secret backend is unsupported.")

    address = environment.get("JASON_OPENBAO_ADDR", "http://127.0.0.1:8200").strip()
    token_file = environment.get("JASON_OPENBAO_TOKEN_FILE", "").strip()
    if not token_file:
        raise ProviderUnauthorizedError("OpenBao token file is not configured.")
    return OpenBaoBackend(address=address, token_file=Path(token_file).expanduser())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jason-secret",
        description="Resolve one governed logical secret without exposing diagnostics on stdout.",
    )
    parser.add_argument("logical_name", nargs="?")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--contract-test", metavar="LOGICAL_NAME")
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=Path("/etc/jason/secret-mappings.json"),
    )
    return parser


def run(argv: Sequence[str] | None = None, *, environment: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ if environment is None else environment
    try:
        backend = build_backend(env)
        if args.health:
            if args.logical_name or args.contract_test:
                raise SecretMalformedError("Health mode cannot be combined with resolution modes.")
            backend.health()
            print("healthy")
            return 0

        logical_name = args.contract_test or args.logical_name
        if not logical_name:
            raise SecretMalformedError("A logical secret name is required.")
        mappings = load_mappings(args.mapping_file.expanduser())
        mapping = resolve_mapping(mappings, logical_name)
        value = backend.resolve(mapping.provider_path, mapping.field)

        if args.contract_test:
            print("contract-ok")
        else:
            sys.stdout.write(value + "\n")
        return 0
    except SecretProviderError as exc:
        print(f"DENIED: {exc}", file=sys.stderr)
        return exc.exit_code


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
