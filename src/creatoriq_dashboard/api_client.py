"""A small, resilient REST client for the CreatorIQ API.

Verified against a live CreatorIQ account (see config/endpoints.yaml for the
confirmed base URL, auth scheme, and per-resource quirks). CreatorIQ's public
API reference (apidocs.creatoriq.com) is gated behind an account login, and
some resource shapes are genuinely inconsistent across endpoints (e.g. list
results are sometimes a JSON array and sometimes a ``{"0": {...}, "1": {...}}``
object, and pagination metadata lives in different places depending on the
resource) -- this client normalizes those differences so the rest of the
codebase can just work with plain lists of dicts.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterator

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import AppConfig

logger = logging.getLogger(__name__)


class CreatorIQAPIError(RuntimeError):
    """Raised when the CreatorIQ API returns a non-retryable error."""


class CreatorIQRateLimitError(RuntimeError):
    """Raised on HTTP 429; retried with backoff by the caller."""


def get_path(obj: Any, dotted_path: str, default: Any = None) -> Any:
    """Read a possibly-nested value out of a dict using a dotted path.

    Example: get_path({"Publisher": {"Id": 7}}, "Publisher.Id") -> 7
    """
    if not dotted_path:
        return default
    node = obj
    for part in dotted_path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def coerce_to_record_list(value: Any) -> list[dict[str, Any]]:
    """CreatorIQ list endpoints are inconsistent: some return a JSON array,
    others return an object keyed by string indices ("0", "1", "2", ...).
    Normalize both shapes into a plain list.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        try:
            return [value[k] for k in sorted(value.keys(), key=int)]
        except (ValueError, TypeError):
            return list(value.values())
    raise CreatorIQAPIError(f"Expected a list or indexed dict of records, got {type(value).__name__}")


def unwrap_items(records: list[dict[str, Any]], unwrap_key: str | None) -> list[dict[str, Any]]:
    """Some collections wrap each item as {"type": "...", "href": "...", "<Key>": {...actual fields...}}.
    If unwrap_key is set, pull the inner dict out; otherwise return records unchanged.
    """
    if not unwrap_key:
        return records
    return [r.get(unwrap_key, r) if isinstance(r, dict) else r for r in records]


class CreatorIQClient:
    """Thin wrapper around ``requests`` that knows how to page through
    CreatorIQ endpoints as configured in ``config/endpoints.yaml``.
    """

    def __init__(self, config: AppConfig, session: requests.Session | None = None):
        if not config.api_key:
            raise CreatorIQAPIError(
                "CREATORIQ_API_KEY is not set. Add it to your .env file "
                "(see .env.example) before using live mode."
            )
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.api_key}",
                "Accept": "application/json",
            }
        )
        if config.org_id:
            self.session.headers["X-CreatorIQ-Org-Id"] = config.org_id

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((CreatorIQRateLimitError, requests.ConnectionError, requests.Timeout)),
    )
    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, params=params, timeout=30)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", 2))
            logger.warning("CreatorIQ rate limit hit, sleeping %.1fs", retry_after)
            time.sleep(retry_after)
            raise CreatorIQRateLimitError(f"Rate limited on {path}")
        if response.status_code >= 500:
            raise requests.ConnectionError(f"CreatorIQ 5xx on {path}: {response.status_code}")
        if response.status_code >= 400:
            raise CreatorIQAPIError(
                f"CreatorIQ API error {response.status_code} on {path}: {response.text[:500]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise CreatorIQAPIError(f"Non-JSON response from {path}") from exc

    def _resource_cfg(self, resource_name: str) -> dict[str, Any]:
        resources = self.config.endpoints.get("resources", {})
        if resource_name not in resources:
            raise CreatorIQAPIError(f"Unknown resource '{resource_name}'. Add it to config/endpoints.yaml.")
        return resources[resource_name]

    # ------------------------------------------------------------------
    # Flat, top-level list resources: /publishers, /campaigns, and
    # /publisher/{id}/messages all share the same shape -- a top-level
    # {count, total, page, "<ResultKey>": [...] } envelope, paginated by
    # incrementing ?page= until a short/empty page comes back.
    # ------------------------------------------------------------------
    def iter_resource(
        self,
        resource_name: str,
        path_params: dict[str, Any] | None = None,
        extra_params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield every record from a configured list resource, handling pagination."""
        resource_cfg = self._resource_cfg(resource_name)
        pagination_cfg = self.config.endpoints.get("pagination", {})
        path = resource_cfg["path"].format(**(path_params or {}))
        method = resource_cfg.get("method", "GET")

        params: dict[str, Any] = dict(resource_cfg.get("params", {}) or {})
        if extra_params:
            params.update(extra_params)
        params = {k: v for k, v in params.items() if v is not None and v != ""}

        style = pagination_cfg.get("style", "page")
        results_path = resource_cfg.get("results_path", pagination_cfg.get("results_path", "data"))
        unwrap_key = resource_cfg.get("item_unwrap_key")
        page_size = resource_cfg.get("page_size", pagination_cfg.get("page_size", 100))

        page_number = 1
        offset = 0
        cursor: str | None = None
        pages_fetched = 0

        while True:
            page_params = dict(params)
            if style == "page":
                page_params[pagination_cfg.get("page_param", "page")] = page_number
                page_params[pagination_cfg.get("page_size_param", "page_size")] = page_size
            elif style == "offset":
                page_params[pagination_cfg.get("offset_param", "offset")] = offset
                page_params[pagination_cfg.get("limit_param", "limit")] = page_size
            elif style == "cursor" and cursor:
                page_params[pagination_cfg.get("cursor_param", "cursor")] = cursor

            payload = self._request(method, path, params=page_params)
            records = coerce_to_record_list(get_path(payload, results_path, default=[]))
            records = unwrap_items(records, unwrap_key)
            for record in records:
                yield record

            pages_fetched += 1
            if max_pages is not None and pages_fetched >= max_pages:
                break
            if not records:
                break

            if style == "page":
                total_pages = get_path(payload, pagination_cfg.get("total_pages_path", ""))
                has_more = get_path(payload, pagination_cfg.get("has_more_path", ""))
                page_number += 1
                if has_more is False:
                    break
                if total_pages is not None and page_number > total_pages:
                    break
                if has_more is None and total_pages is None and len(records) < page_size:
                    break
            elif style == "offset":
                offset += page_size
                if len(records) < page_size:
                    break
            elif style == "cursor":
                cursor = get_path(payload, pagination_cfg.get("next_cursor_path", ""))
                if not cursor:
                    break
            else:
                break

    def fetch_all(
        self,
        resource_name: str,
        path_params: dict[str, Any] | None = None,
        extra_params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        return list(
            self.iter_resource(resource_name, path_params=path_params, extra_params=extra_params, max_pages=max_pages)
        )

    # ------------------------------------------------------------------
    # Nested-pagination resources: /campaign/{id}/activity returns
    # {"CampaignActivity": {"totals": {...}, "items": [...], "pagination":
    # {"total_pages": N, "page": "1", "size": 20}}} -- pagination info lives
    # *inside* the wrapper object rather than at the top level.
    # ------------------------------------------------------------------
    def iter_nested_resource(
        self,
        resource_name: str,
        path_params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        resource_cfg = self._resource_cfg(resource_name)
        path = resource_cfg["path"].format(**(path_params or {}))
        method = resource_cfg.get("method", "GET")
        wrapper_key = resource_cfg["wrapper_key"]
        items_key = resource_cfg.get("items_key", "items")
        pagination_key = resource_cfg.get("pagination_key", "pagination")
        page_param = resource_cfg.get("page_param", "page")
        page_size_param = resource_cfg.get("page_size_param")
        page_size = resource_cfg.get("page_size")

        page_number = 1
        pages_fetched = 0
        while True:
            params = {page_param: page_number}
            if page_size_param and page_size:
                params[page_size_param] = page_size
            payload = self._request(method, path, params=params)
            wrapper = payload.get(wrapper_key, {})
            items = coerce_to_record_list(wrapper.get(items_key, []))
            for item in items:
                yield item

            pages_fetched += 1
            if max_pages is not None and pages_fetched >= max_pages:
                break
            if not items:
                break

            pagination = wrapper.get(pagination_key, {}) or {}
            total_pages = pagination.get("total_pages")
            page_number += 1
            if total_pages is not None and page_number > int(total_pages):
                break
            if total_pages is None and len(items) < 1:
                break

    def fetch_nested_all(
        self, resource_name: str, path_params: dict[str, Any] | None = None, max_pages: int | None = None
    ) -> list[dict[str, Any]]:
        return list(self.iter_nested_resource(resource_name, path_params=path_params, max_pages=max_pages))

    # ------------------------------------------------------------------
    # Single-fetch resources: either a genuinely unpaginated list
    # (/campaign/{id}/publishers ignores ?page= and always returns
    # everything) or a single object (/publisher/{id}/summary).
    # ------------------------------------------------------------------
    def fetch_unpaginated_list(self, resource_name: str, path_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        resource_cfg = self._resource_cfg(resource_name)
        path = resource_cfg["path"].format(**(path_params or {}))
        method = resource_cfg.get("method", "GET")
        results_path = resource_cfg["results_path"]
        unwrap_key = resource_cfg.get("item_unwrap_key")

        payload = self._request(method, path)
        records = coerce_to_record_list(get_path(payload, results_path, default=[]))
        return unwrap_items(records, unwrap_key)

    def fetch_object(self, resource_name: str, path_params: dict[str, Any] | None = None) -> dict[str, Any]:
        resource_cfg = self._resource_cfg(resource_name)
        path = resource_cfg["path"].format(**(path_params or {}))
        method = resource_cfg.get("method", "GET")
        result_key = resource_cfg.get("result_key")
        payload = self._request(method, path)
        return get_path(payload, result_key, default=payload) if result_key else payload

    # ------------------------------------------------------------------
    # ID resolution: CreatorIQ's campaign-scoped endpoints identify
    # creators by an internal numeric "Id", but per-creator sub-resources
    # (/publisher/{id}/summary, /publisher/{id}/messages) require the
    # longer "NetworkPublisherId". Resolve via the /publishers search
    # filter when a post/activity record didn't already give us both.
    # ------------------------------------------------------------------
    def resolve_network_publisher_id(self, internal_publisher_id: int | str) -> str | None:
        resource_cfg = self._resource_cfg("publishers")
        path = resource_cfg["path"]
        payload = self._request("GET", path, params={"filter": f"Id={internal_publisher_id}"})
        results_path = resource_cfg.get("results_path", "PublisherCollection")
        unwrap_key = resource_cfg.get("item_unwrap_key")
        records = unwrap_items(coerce_to_record_list(get_path(payload, results_path, default=[])), unwrap_key)
        if not records:
            return None
        return records[0].get("NetworkPublisherId")
