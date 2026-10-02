from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.service import InvocationResult

CAPABILITY = "procurement.web.product.read"
PROVIDER = "public_web_procurement"
PROFILE_ENV = "JASON_PROCUREMENT_WEB_READ_PROFILE"
PROFILE = "procurement-web-v1"
DEFAULT_MAX_BYTES = 1_500_000
HARD_MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3


class ProcurementWebReadError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        acquisition_hint: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.acquisition_hint = acquisition_hint
        self.http_status = http_status


def _resolve_public_host(host: str) -> None:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProcurementWebReadError("product URL host could not be resolved") from exc
    addresses = {record[4][0] for record in records}
    if not addresses:
        raise ProcurementWebReadError("product URL host returned no addresses")
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise ProcurementWebReadError("product URL resolved to an invalid address") from exc
        if not address.is_global:
            raise ProcurementWebReadError(
                "product URL resolved to a non-public address"
            )


def validate_public_https_url(url: str) -> str:
    value = str(url or "").strip()
    if not value or len(value) > 4096:
        raise ProcurementWebReadError("product URL is missing or too long")
    parsed = urlsplit(value)
    if parsed.scheme.casefold() != "https":
        raise ProcurementWebReadError("product URL must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ProcurementWebReadError("product URL authority is invalid")
    if parsed.port not in (None, 443):
        raise ProcurementWebReadError("product URL must use the standard HTTPS port")
    _resolve_public_host(parsed.hostname)
    return parsed.geturl()


class _ProductPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self.text_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.attribute_hints: dict[str, str] = {}
        self._in_title = False
        self._in_h1 = False
        self._in_jsonld = False
        self._ignored_text_depth = 0
        self._text_itemprop_stack: list[tuple[str, str]] = []
        self._jsonld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        lowered = tag.casefold()
        if lowered == "title":
            self._in_title = True
        elif lowered == "h1":
            self._in_h1 = True
        elif lowered == "meta":
            key = (
                values.get("property")
                or values.get("name")
                or values.get("itemprop")
                or ""
            ).strip().casefold()
            content = values.get("content", "").strip()
            if key and content and len(key) <= 128 and len(content) <= 4096:
                self.meta.setdefault(key, content)
        elif lowered == "script":
            script_type = values.get("type", "").strip().casefold()
            if script_type == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_parts = []
            else:
                self._ignored_text_depth += 1
        elif lowered in {"style", "noscript"}:
            self._ignored_text_depth += 1

        itemprop = values.get("itemprop", "").strip().casefold()
        content = values.get("content", "").strip()
        if itemprop and content:
            generic_itemprops = {
                "price": "price",
                "sku": "sku",
                "mpn": "mpn",
                "model": "mpn",
                "brand": "brand",
                "gtin": "upc",
                "gtin12": "upc",
                "gtin13": "upc",
                "upc": "upc",
            }
            canonical = generic_itemprops.get(itemprop)
            if canonical:
                self.attribute_hints.setdefault(canonical, content)
        elif itemprop:
            generic_text_itemprops = {
                "sku": "sku",
                "mpn": "mpn",
                "model": "mpn",
                "brand": "brand",
                "gtin": "upc",
                "gtin12": "upc",
                "gtin13": "upc",
                "upc": "upc",
            }
            canonical = generic_text_itemprops.get(itemprop)
            if canonical:
                self._text_itemprop_stack.append((lowered, canonical))

        attribute_sources = {
            "price": ("data-price", "data-product-price", "data-pp-amount"),
            "sku": ("data-sku", "data-item-number", "data-product-sku"),
            "mpn": ("data-mpn", "data-model", "spex-mfg-part-number"),
            "brand": ("data-brand", "data-manufacturer", "spex-mfg-name"),
            "seller": ("data-seller", "data-seller-name"),
            "upc": ("data-upc", "data-gtin", "data-gtin12", "data-gtin13"),
        }
        for canonical, source_keys in attribute_sources.items():
            for source_key in source_keys:
                hint = values.get(source_key, "").strip()
                if hint:
                    self.attribute_hints.setdefault(canonical, hint)
                    break

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "title":
            self._in_title = False
        elif lowered == "h1":
            self._in_h1 = False
        elif lowered == "script":
            if self._in_jsonld:
                value = "".join(self._jsonld_parts).strip()
                if value and sum(len(item) for item in self.jsonld) < 300_000:
                    self.jsonld.append(value[:150_000])
                self._jsonld_parts = []
                self._in_jsonld = False
            elif self._ignored_text_depth:
                self._ignored_text_depth -= 1
        elif lowered in {"style", "noscript"} and self._ignored_text_depth:
            self._ignored_text_depth -= 1

        if self._text_itemprop_stack and self._text_itemprop_stack[-1][0] == lowered:
            self._text_itemprop_stack.pop()

    def handle_data(self, data: str) -> None:
        value = " ".join(str(data).split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        elif self._in_jsonld:
            self._jsonld_parts.append(data)
        elif self._ignored_text_depth:
            return
        elif self._text_itemprop_stack:
            _, canonical = self._text_itemprop_stack[-1]
            if len(value) <= 256:
                self.attribute_hints.setdefault(canonical, value)
            if len(" ".join(self.text_parts)) < 40_000:
                self.text_parts.append(value)
        elif self._in_h1:
            self.h1_parts.append(value)
            if len(" ".join(self.text_parts)) < 40_000:
                self.text_parts.append(value)
        elif len(" ".join(self.text_parts)) < 40_000:
            self.text_parts.append(value)


def _walk_json(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _name(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        return str(value.get("name") or "").strip() or None
    return None


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value).strip() or None
    return None


def _address(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    fields = {
        "street": "streetAddress",
        "city": "addressLocality",
        "state": "addressRegion",
        "postal_code": "postalCode",
        "country": "addressCountry",
    }
    result = {}
    for target, source in fields.items():
        raw = str(value.get(source) or "").strip()
        if raw:
            result[target] = raw
    return result


def _first_price(text: str) -> str | None:
    match = re.search(r"(?<![A-Za-z0-9])\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", text)
    if not match:
        return None
    return match.group(1).replace(",", "")


def _generic_label_value(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    value = str(match.group(1) or "").strip().strip(" |,;")
    return value or None


def _commerce_identifiers(text: str) -> dict[str, str]:
    """Extract common commerce identifiers without vendor-specific branching."""
    mpn = _generic_label_value(
        text,
        r"\b(?:Mfg|Mfr|Manufacturer)\s*(?:Part(?:\s*(?:Number|No\.?|#))?|#)\s*:?[\s|]*"
        r"([A-Za-z0-9][A-Za-z0-9._/+\-]{1,99})\b",
    )
    if not mpn:
        mpn = _generic_label_value(
            text,
            r"\bModel\s*(?:Number|No\.?|#)?\s*:?[\s|]*"
            r"([A-Za-z0-9][A-Za-z0-9._/+\-]{1,99})\b",
        )
    sku = _generic_label_value(
        text,
        r"\b(?:Item|SKU|Product)\s*(?:Number|No\.?|#)\s*:?[\s|]*"
        r"([A-Za-z0-9][A-Za-z0-9._/+\-]{1,99})\b",
    )
    if not sku:
        sku = _generic_label_value(
            text,
            r"\bASIN\s*:?[\s|]*([A-Z0-9]{8,20})\b",
        )
    upc = _generic_label_value(
        text,
        r"\bUPC\s*(?:Number|No\.?|#)?\s*:?[\s|]*([0-9]{8,14})\b",
    )
    result: dict[str, str] = {}
    if mpn:
        result["mpn"] = mpn
    if sku:
        result["sku"] = sku
    if upc:
        result["upc"] = upc
    return result


def _rendered_text_product_fallback(
    parser: _ProductPageParser,
    *,
    title: str,
    excerpt: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Derive a bounded product from explicit rendered-page evidence.

    This is intentionally conservative. It is only used when JSON-LD did not
    provide a Product and requires a name, a verified page price, and at least
    one stable product identifier (MPN/model or vendor SKU).
    """

    heading = " ".join(parser.h1_parts).strip()
    name = heading or parser.meta.get("og:title") or title
    price = parser.attribute_hints.get("price") or _first_price(excerpt)
    labels = _commerce_identifiers(excerpt)
    mpn = parser.attribute_hints.get("mpn") or labels.get("mpn")
    sku = parser.attribute_hints.get("sku") or labels.get("sku")
    upc = parser.attribute_hints.get("upc") or labels.get("upc")

    seller = parser.attribute_hints.get("seller")
    if not seller:
        seller_match = re.search(
            r"\bSold\s+by\s+(.{2,100}?)(?=\s+(?:Top\s+Rated|Shipped\s+by|Contact\s+Seller|Price\s+alert|Add\s+to\s+cart)\b)",
            excerpt,
            re.I,
        )
        if seller_match:
            seller = " ".join(seller_match.group(1).split()).strip(" -|")

    if not (name and price and (mpn or sku)):
        return None, None

    product = {
        "name": name,
        "sku": sku,
        "mpn": mpn,
        "brand": parser.attribute_hints.get("brand"),
        "upc": upc,
        "price": price,
        "currency": "USD" if "$" in excerpt or parser.attribute_hints.get("price") else None,
        "seller": seller,
    }
    product = {key: value for key, value in product.items() if value}

    organization = {"name": seller} if seller else None
    return product, organization


def _normalize_product_identifiers(product: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(product)
    mpn = str(normalized.get("mpn") or "").strip()
    upc = str(normalized.get("upc") or "").strip()
    if mpn and upc and mpn == upc and mpn.isdigit() and 8 <= len(mpn) <= 14:
        # Some commerce feeds duplicate the GTIN/UPC into the MPN field. Preserve
        # the barcode as a secondary identifier and let a distinct SKU/model win.
        normalized.pop("mpn", None)
        normalized["identifier_note"] = "source_mpn_duplicated_upc"
    return normalized


def extract_product_page(html: str) -> dict[str, Any]:
    parser = _ProductPageParser()
    parser.feed(html)
    products: list[dict[str, Any]] = []
    organizations: list[dict[str, Any]] = []

    decoded: list[Any] = []
    for raw in parser.jsonld:
        try:
            decoded.append(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    for obj in _walk_json(decoded):
        raw_type = obj.get("@type")
        types = (
            {str(item).casefold() for item in raw_type}
            if isinstance(raw_type, list)
            else {str(raw_type or "").casefold()}
        )
        if "product" in types:
            offer = obj.get("offers")
            if isinstance(offer, list):
                offer = next((item for item in offer if isinstance(item, Mapping)), {})
            if not isinstance(offer, Mapping):
                offer = {}
            product = {
                "name": _name(obj.get("name")),
                "description": _name(obj.get("description")),
                "sku": _name(obj.get("sku")),
                "mpn": _name(obj.get("mpn")),
                "brand": _name(obj.get("brand")),
                "upc": (
                    _scalar_text(obj.get("gtin12"))
                    or _scalar_text(obj.get("gtin13"))
                    or _scalar_text(obj.get("gtin"))
                    or _scalar_text(obj.get("upc"))
                ),
                "price": _scalar_text(
                    offer.get("price")
                    if offer.get("price") is not None
                    else offer.get("lowPrice")
                ),
                "currency": _name(offer.get("priceCurrency")),
                "availability": _name(offer.get("availability")),
                "seller": _name(offer.get("seller")),
            }
            cleaned = {k: v for k, v in product.items() if v}
            if cleaned:
                products.append(cleaned)

        if "organization" in types or "corporation" in types or "localbusiness" in types:
            org = {
                "name": _name(obj.get("name")),
                "url": _name(obj.get("url")),
                "phone": _name(obj.get("telephone")),
                "email": _name(obj.get("email")),
                "address": _address(obj.get("address")),
            }
            cleaned = {
                k: v for k, v in org.items()
                if v not in (None, "", {})
            }
            if cleaned:
                organizations.append(cleaned)

    title = " ".join(parser.title_parts).strip()
    excerpt = " ".join(parser.text_parts)
    if len(excerpt) > 40_000:
        excerpt = excerpt[:40_000]

    if not products:
        fallback_product, fallback_org = _rendered_text_product_fallback(
            parser,
            title=title,
            excerpt=excerpt,
        )
        if fallback_product:
            products.append(fallback_product)
        if fallback_org:
            organizations.append(fallback_org)

    products = [_normalize_product_identifiers(item) for item in products]
    normalization_status = "ready" if products else "needs_richer_acquisition"
    evidence_mode = (
        "structured_or_semantic_product"
        if parser.jsonld and products
        else ("rendered_product" if products else "none")
    )

    products.sort(key=lambda item: len(item), reverse=True)
    organizations.sort(
        key=lambda item: (bool(item.get("address")), len(item)),
        reverse=True,
    )
    return {
        "page_title": title or None,
        "meta": dict(sorted(parser.meta.items())),
        "products": products[:10],
        "organizations": organizations[:10],
        "normalization_status": normalization_status,
        "evidence_mode": evidence_mode,
        "visible_text_excerpt": excerpt,
    }


def _fetch_html(url: str, *, max_bytes: int) -> tuple[str, str, bool]:
    current = validate_public_https_url(url)
    context = ssl.create_default_context()
    for redirect_count in range(MAX_REDIRECTS + 1):
        parsed = urlsplit(current)
        host = parsed.hostname or ""
        _resolve_public_host(host)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        connection = http.client.HTTPSConnection(
            host,
            port=443,
            timeout=15,
            context=context,
        )
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": "Project-Jason-Procurement/1.0",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            status = int(response.status)
            if status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                response.read(4096)
                if not location or redirect_count >= MAX_REDIRECTS:
                    raise ProcurementWebReadError("product URL redirect chain is invalid")
                current = validate_public_https_url(urljoin(current, location))
                continue
            if status != 200:
                if status in {401, 403, 429}:
                    raise ProcurementWebReadError(
                        f"product URL returned HTTP {status}",
                        acquisition_hint="browser_or_api",
                        http_status=status,
                    )
                raise ProcurementWebReadError(
                    f"product URL returned HTTP {status}"
                )
            content_type = str(response.getheader("Content-Type") or "").casefold()
            if not (
                content_type.startswith("text/html")
                or content_type.startswith("application/xhtml+xml")
            ):
                raise ProcurementWebReadError(
                    "product URL did not return an HTML document"
                )
            payload = response.read(max_bytes + 1)
            truncated = len(payload) > max_bytes
            payload = payload[:max_bytes]
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
            try:
                html = payload.decode(charset or "utf-8", errors="replace")
            except LookupError:
                html = payload.decode("utf-8", errors="replace")
            return current, html, truncated
        finally:
            connection.close()
    raise ProcurementWebReadError("product URL exceeded redirect limit")


@dataclass(frozen=True, slots=True)
class ProcurementWebReadInvoker:
    def invoke(self, *, request, resolution):
        if request.capability_name != CAPABILITY:
            raise PermissionError("procurement web capability mismatch")
        if resolution.selected_provider_id != PROVIDER:
            raise PermissionError("procurement web provider mismatch")
        args = dict(request.arguments or {})
        if set(args) - {"url", "max_bytes"}:
            raise ValueError("unsupported procurement web arguments")
        raw_max = args.get("max_bytes", DEFAULT_MAX_BYTES)
        if isinstance(raw_max, bool):
            raise ValueError("max_bytes must be an integer")
        max_bytes = int(raw_max)
        if max_bytes < 32_768 or max_bytes > HARD_MAX_BYTES:
            raise ValueError("max_bytes is outside the bounded range")

        source_url = validate_public_https_url(str(args.get("url") or ""))
        captured_at = datetime.now(timezone.utc).isoformat()
        try:
            final_url, html, truncated = _fetch_html(source_url, max_bytes=max_bytes)
        except ProcurementWebReadError as exc:
            if exc.acquisition_hint != "browser_or_api":
                raise
            return InvocationResult(
                output={
                    "provider": PROVIDER,
                    "source_url": source_url,
                    "final_url": source_url,
                    "source_host": urlsplit(source_url).hostname,
                    "captured_at": captured_at,
                    "content_sha256": None,
                    "truncated": False,
                    "page_title": None,
                    "meta": {},
                    "products": [],
                    "organizations": [],
                    "normalization_status": "needs_browser_or_api",
                    "evidence_mode": "simple_http_blocked",
                    "fetch_http_status": exc.http_status,
                    "acquisition_hint": exc.acquisition_hint,
                    "visible_text_excerpt": "",
                },
                attempts=1,
            )

        facts = extract_product_page(html)
        digest = sha256(html.encode("utf-8", errors="replace")).hexdigest()
        return InvocationResult(
            output={
                "provider": PROVIDER,
                "source_url": source_url,
                "final_url": final_url,
                "source_host": urlsplit(final_url).hostname,
                "captured_at": captured_at,
                "content_sha256": digest,
                "truncated": truncated,
                **facts,
            },
            attempts=1,
        )


def register_foundation(*, capabilities, providers, now: datetime) -> None:
    capability = CapabilityDefinition(
        capability_name=CAPABILITY,
        version="1.0",
        display_name="Read Public Procurement Product Page",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Read one public HTTPS product page for AOT procurement evidence, "
            "pricing, vendor verification, and catalog normalization."
        ),
        owner_service="Jason Procurement",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"public", "internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/procurement-web-product-read/1.0",
        output_schema_reference="schema://jason/procurement-web-product-read-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("source URL", "capture timestamp", "content digest"),
            verification_requirements=(
                "HTTPS only",
                "all resolved addresses are public",
                "bounded response size and redirects",
            ),
        ),
        dependencies=frozenset({"identity.authorization.resolve"}),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without credentials, private-address access, "
            "redirect bypass, or non-HTML fallback."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Allow technicians to paste a public product URL into the governed "
                "procurement workflow without granting Jason general browser authority."
            ),
            review_interval_days=30,
            retirement_criteria=("Public URL containment cannot be proven.",),
            authoritative_change_sources=("Python standard library",),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "procurement_product_page,public_web_page",
            "operation": "read",
            "selector_keys": "url,max_bytes",
            "fact_hints": (
                "product url website retailer vendor price availability sku mpn "
                "manufacturer model address phone email"
            ),
            "canonical_facts": (
                "page_title,products,organizations,meta,final_url,captured_at"
            ),
        },
    )
    capabilities.register(capability)

    provider = ExecutionProvider(
        provider_id=PROVIDER,
        display_name="Bounded Public Procurement Web",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({CAPABILITY}),
        supported_classifications=frozenset({"public", "internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=2,
            maximum_requests_per_minute=30,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Use a bounded credential-free HTTPS reader for procurement evidence."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Public-network containment cannot be proven.",),
            vendor_change_sources=("Python standard library",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={"read_only": "true"},
    )
    providers.register(provider)
    if os.getenv(PROFILE_ENV, "").strip().casefold() == PROFILE:
        capabilities.set_lifecycle(
            capability_name=CAPABILITY,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
        providers.set_approval(
            provider_id=PROVIDER,
            approval_status=ProviderApproval.APPROVED,
        )
        providers.set_health(
            provider_id=PROVIDER,
            health_status=ProviderHealth.HEALTHY,
        )
        providers.set_lifecycle(
            provider_id=PROVIDER,
            lifecycle_status=ProviderLifecycle.AVAILABLE,
        )


def build_invoker() -> ProcurementWebReadInvoker:
    return ProcurementWebReadInvoker()
