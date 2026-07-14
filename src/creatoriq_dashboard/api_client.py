"""A small, resilient REST client for the CreatorIQ API.

CreatorIQ's public API reference is gated behind an account login, and the
exact resource paths / pagination style can vary by account. Rather than
hard-coding assumptions, this client reads its endpoint paths and pagination
strategy from ``config/endpoints.yaml`` so you can align it with your
account's real API docs / Postman collection without touching Python code.
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
    node = obj
    for part in dotted_path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


class CreatorIQClient:
    """Thin wrapper around ``requests`` that knows how to page through
    CreatorIQ list endpoints as configured in ``config/endpoints.yaml``.
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

    def iter_resource(
        self,
        resource_name: str,
        extra_params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield every record from a configured list resource, handling pagination."""
        resources = self.config.endpoints.get("resources", {})
        if resource_name not in resources:
            raise CreatorIQAPIError(
                f"Unknown resource '{resource_name}'. Add it to config/endpoints.yaml."
            )
        resource_cfg = resources[resource_name]
        pagination_cfg = self.config.endpoints.get("pagination", {})
        path = resource_cfg["path"]
        method = resource_cfg.get("method", "GET")

        params: dict[str, Any] = dict(resource_cfg.get("params", {}) or {})
        if extra_params:
            params.update(extra_params)
        params = {k: v for k, v in params.items() if v is not None and v != ""}

        style = pagination_cfg.get("style", "page")
        results_path = pagination_cfg.get("results_path", "data")
        page_size = pagination_cfg.get("page_size", 100)

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
            records = get_path(payload, results_path, default=[]) or []
            if not isinstance(records, list):
                raise CreatorIQAPIError(
                    f"Expected a list at '{results_path}' for resource '{resource_name}', "
                    f"got {type(records).__name__}. Check config/endpoints.yaml results_path."
                )
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
        extra_params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        return list(self.iter_resource(resource_name, extra_params=extra_params, max_pages=max_pages))
