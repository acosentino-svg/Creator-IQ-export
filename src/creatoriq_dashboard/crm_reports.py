"""CreatorIQ CRM Reports API — async view reports (Active Members, etc.).

Uses the CRM API documented at apis.creatoriq.com (x-api-key auth), separate
from the ExchangeIQ API at api.creatoriq.com/api (Bearer auth).

Pattern (verified from Daily Campaign Posts docs):
  1. GET /crm/v1/api/view?view=Reports/...&requestData[take]=N → TaskId + CREATED
  2. Poll same URL with taskId=... until TaskStatus=DONE
  3. Download file from Result.Headers.Location
"""
from __future__ import annotations

import io
import logging
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from .active_members import merge_active_member_link_frames, parse_active_members_csv
from .config import AppConfig
from .storage import get_engine, read_table, record_sync, write_table

logger = logging.getLogger(__name__)


class CRMReportError(RuntimeError):
    pass


def _crm_headers(config: AppConfig) -> dict[str, str]:
    if not config.api_key:
        raise CRMReportError("CREATORIQ_API_KEY is not set")
    return {"x-api-key": config.api_key, "Accept": "application/json, text/csv, */*"}


def _extract_location(result: Any) -> str | None:
    if not result:
        return None
    if isinstance(result, dict):
        headers = result.get("Headers") or result.get("headers") or {}
        if isinstance(headers, dict):
            loc = headers.get("Location") or headers.get("location")
            if loc:
                return str(loc)
    return None


def _poll_report_task(
    session: requests.Session,
    config: AppConfig,
    view: str,
    task_id: str,
    poll_interval: float,
    poll_timeout: float,
) -> str:
    """Poll until TaskStatus=DONE; return download Location URL."""
    deadline = time.time() + poll_timeout
    poll_url = f"{config.crm_base_url.rstrip('/')}/api/view"
    while time.time() < deadline:
        for params in (
            {"view": view, "taskId": task_id},
            {"view": view, "TaskId": task_id},
            {"taskId": task_id},
        ):
            try:
                resp = session.get(poll_url, params=params, timeout=60)
            except requests.RequestException as exc:
                logger.warning("CRM poll request failed: %s", exc)
                continue
            if resp.status_code >= 400:
                continue
            try:
                payload = resp.json()
            except ValueError:
                continue
            status = str(payload.get("TaskStatus", "")).upper()
            if status in ("CREATED", "PROCESSING", ""):
                break
            if status == "DONE":
                location = _extract_location(payload.get("Result"))
                if location:
                    return location
                raise CRMReportError(f"Report DONE but no Location URL in response: {payload!r}")
            if status == "FAILED":
                raise CRMReportError(f"CRM report task failed: {payload!r}")
        time.sleep(poll_interval)
    raise CRMReportError(f"Timed out waiting for CRM report task {task_id} (view={view})")


def _start_report_page(
    session: requests.Session,
    config: AppConfig,
    view: str,
    take: int,
    skip: int,
) -> str:
    url = f"{config.crm_base_url.rstrip('/')}/api/view"
    params = {
        "view": view,
        "requestData[take]": take,
        "requestData[skip]": skip,
        "section": "default",
    }
    resp = session.get(url, params=params, timeout=60)
    if resp.status_code >= 400:
        raise CRMReportError(f"CRM report start failed ({resp.status_code}): {resp.text[:500]}")
    payload = resp.json()
    task_id = payload.get("TaskId") or payload.get("taskId")
    if not task_id:
        raise CRMReportError(f"No TaskId in CRM report response: {payload!r}")
    return str(task_id)


def _download_report_file(session: requests.Session, location: str) -> bytes:
    resp = session.get(location, timeout=120, allow_redirects=True)
    if resp.status_code >= 400:
        raise CRMReportError(f"Download failed ({resp.status_code}) from {location[:120]}")
    return resp.content


def _bytes_to_dataframe(content: bytes) -> pd.DataFrame:
    text = content.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return pd.DataFrame()
    if text.startswith("{") or text.startswith("["):
        try:
            import json

            data = json.loads(text)
            if isinstance(data, list):
                return pd.DataFrame(data)
            if isinstance(data, dict):
                for key in ("data", "rows", "items", "PublisherCollection", "Creators"):
                    if key in data and isinstance(data[key], list):
                        return pd.DataFrame(data[key])
                return pd.DataFrame([data])
        except ValueError:
            pass
    return pd.read_csv(io.BytesIO(content))


def fetch_crm_report_dataframe(
    config: AppConfig,
    view: str,
    *,
    page_size: int = 500,
    max_pages: int = 100,
    poll_interval: float = 3.0,
    poll_timeout: float = 300.0,
) -> pd.DataFrame:
    """Fetch one CRM view report, paginating with requestData[skip]/[take]."""
    session = requests.Session()
    session.headers.update(_crm_headers(config))
    frames: list[pd.DataFrame] = []

    for page in range(max_pages):
        skip = page * page_size
        logger.info("CRM report %s: starting page skip=%d take=%d", view, skip, page_size)
        task_id = _start_report_page(session, config, view, take=page_size, skip=skip)
        location = _poll_report_task(session, config, view, task_id, poll_interval, poll_timeout)
        raw = _download_report_file(session, location)
        df = _bytes_to_dataframe(raw)
        if df.empty:
            break
        frames.append(df)
        logger.info("CRM report %s: page %d returned %d rows", view, page + 1, len(df))
        if len(df) < page_size:
            break

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def sync_active_member_links_from_crm(config: AppConfig) -> int:
    """Pull Active Members (or Creators) report via CRM API → active_member_links table."""
    cfg = config.settings.get("live_sync", "active_members_report", default={}) or {}
    if not cfg.get("enabled", True):
        logger.info("active_members_report sync disabled in settings")
        return 0

    views = cfg.get("view_candidates") or [
        "Reports/ActiveMembers",
        "Reports/ActiveMembersReport",
        "Reports/Creators",
        "Reports/GetCreatorsReport",
    ]
    page_size = int(cfg.get("page_size", 500))
    max_pages = int(cfg.get("max_pages", 100))
    poll_interval = float(cfg.get("poll_interval_seconds", 3))
    poll_timeout = float(cfg.get("poll_timeout_seconds", 300))

    last_error: Exception | None = None
    parsed = pd.DataFrame()
    for view in views:
        try:
            logger.info("Trying CRM report view: %s", view)
            raw_df = fetch_crm_report_dataframe(
                config,
                view,
                page_size=page_size,
                max_pages=max_pages,
                poll_interval=poll_interval,
                poll_timeout=poll_timeout,
            )
            if raw_df.empty:
                logger.warning("CRM view %s returned no rows", view)
                continue
            parsed = parse_active_members_csv(raw_df)
            if not parsed.empty:
                logger.info("CRM view %s parsed %d creator link rows", view, len(parsed))
                break
        except Exception as exc:  # noqa: BLE001
            logger.warning("CRM view %s failed: %s", view, exc)
            last_error = exc

    if parsed.empty:
        if last_error:
            raise CRMReportError(f"All Active Members CRM views failed. Last error: {last_error}") from last_error
        raise CRMReportError("Active Members CRM report returned no link-date rows")

    engine = get_engine(config.db_path)
    existing = read_table(engine, "active_member_links")
    merged = merge_active_member_link_frames(existing, parsed)
    write_table(engine, "active_member_links", merged)
    record_sync(engine, "active_member_links", datetime.now(timezone.utc))
    return len(merged)
