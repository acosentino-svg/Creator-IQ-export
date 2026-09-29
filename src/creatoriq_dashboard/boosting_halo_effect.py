"""Merge CreatorIQ 'posted' export + internal 'selected for boosting' tracker."""
from __future__ import annotations

import io
import re
import zipfile
from urllib.parse import urlparse

import pandas as pd

from creatoriq_dashboard.boosting_rules import is_eligible_boosting_content
from creatoriq_dashboard.boosting_scorecard import CONTENT_RAW_COLUMNS, normalize_content_raw
from creatoriq_dashboard.config import AppConfig, load_config


def _normalize_url_key(url: str) -> str | None:
    """Stable key for matching TikTok video IDs and Instagram reel codes."""
    if url is None or (isinstance(url, float) and pd.isna(url)):
        return None
    text = str(url).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    text = text.split()[0]  # first token if cell has multiple URLs
    if not text.startswith("http"):
        text = "https://" + text.lstrip("/")
    parsed = urlparse(text)
    path = (parsed.path or "").rstrip("/")
    host = (parsed.netloc or "").lower()

    # TikTok: .../video/7568707707776126239
    m = re.search(r"/video/(\d+)", path, flags=re.IGNORECASE)
    if m:
        return f"tiktok:{m.group(1)}"

    # Instagram reel / post / tv
    m = re.search(r"/(?:reel|p|tv)/([^/?#]+)", path, flags=re.IGNORECASE)
    if m:
        return f"instagram:{m.group(1).lower()}"

    # YouTube shorts
    m = re.search(r"/shorts/([^/?#]+)", path, flags=re.IGNORECASE)
    if m:
        return f"youtube:{m.group(1).lower()}"

    # Fallback: host + path without query
    return f"url:{host}{path.lower()}"


def _parse_usage_date(value) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.notna(ts):
        return pd.Timestamp(ts).tz_convert("UTC")
    return None


def parse_halo_selected_csv(source: str | bytes | pd.DataFrame) -> pd.DataFrame:
    """Internal boosting selection tracker (Content Used + Duration of Usage)."""
    raw = pd.read_csv(source) if not isinstance(source, pd.DataFrame) else source.copy()
    if raw.empty:
        return pd.DataFrame(columns=["url_key", "content_url", "selection_date", "platform", "creator_name"])

    col_names = {str(c).strip(): c for c in raw.columns}
    content_col = next((col_names[k] for k in col_names if "content used" in k.lower()), None)
    date_col = next((col_names[k] for k in col_names if "duration" in k.lower() and "usage" in k.lower()), None)
    platform_col = next((col_names[k] for k in col_names if "platform" in k.lower()), None)
    name_col = next((col_names[k] for k in col_names if k.lower() == "creator name"), None)
    asset_col = next((col_names[k] for k in col_names if "creative asset" in k.lower()), None)

    if not content_col:
        raise ValueError("Selected sheet: expected a 'Content Used' column.")

    rows: list[dict] = []
    for _, row in raw.iterrows():
        url = row.get(content_col)
        key = _normalize_url_key(url)
        if not key and asset_col is not None:
            asset = str(row.get(asset_col, "")).strip()
            if asset and asset.lower() not in {"nan", "#ref!"}:
                if asset.isdigit():
                    key = f"tiktok:{asset}"
                else:
                    key = f"instagram:{asset.lower()}"
        if not key:
            continue
        rows.append(
            {
                "url_key": key,
                "content_url": str(url).strip() if url is not None else "",
                "selection_date": _parse_usage_date(row.get(date_col)) if date_col else None,
                "platform": str(row.get(platform_col, "")).strip() if platform_col else "",
                "creator_name_selected": str(row.get(name_col, "")).strip() if name_col else "",
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Keep earliest selection date per asset if duplicated
    out = out.sort_values("selection_date").drop_duplicates(subset=["url_key"], keep="first")
    return out.reset_index(drop=True)


def parse_halo_posted_csv(source: str | bytes | pd.DataFrame) -> pd.DataFrame:
    """CreatorIQ posts export (Post Link, Post Date, Publisher Id, Post Description)."""
    raw = pd.read_csv(source) if not isinstance(source, pd.DataFrame) else source.copy()
    if raw.empty:
        return pd.DataFrame(columns=CONTENT_RAW_COLUMNS)

    link_col = next((c for c in raw.columns if "post link" in c.lower()), None)
    date_col = next((c for c in raw.columns if "post date" in c.lower()), None)
    id_col = next((c for c in raw.columns if "publisher" in c.lower() and "id" in c.lower()), None)
    name_col = next((c for c in raw.columns if "creator name" in c.lower()), None)
    handle_col = next((c for c in raw.columns if "socialhandle" in c.lower().replace(" ", "")), None)
    desc_col = next((c for c in raw.columns if "post description" in c.lower()), None)
    post_id_col = next((c for c in raw.columns if c.strip().lower() == "post id"), None)

    if not link_col or not date_col or not id_col:
        raise ValueError("Posted sheet: need Post Link, Post Date, and Publisher Id columns.")

    rows: list[dict] = []
    for _, row in raw.iterrows():
        link = row.get(link_col)
        key = _normalize_url_key(link)
        if not key and post_id_col:
            key = f"postid:{row.get(post_id_col)}"
        if not key:
            continue
        post_date = pd.to_datetime(row.get(date_col), errors="coerce", utc=True)
        desc = row.get(desc_col) if desc_col else ""
        platform = ""
        if key.startswith("tiktok:"):
            platform = "TikTok"
        elif key.startswith("instagram:"):
            platform = "Instagram"
        elif key.startswith("youtube:"):
            platform = "YouTube"

        rows.append(
            {
                "url_key": key,
                "creator_id": str(row.get(id_col)).strip(),
                "creator_name": str(row.get(name_col, "")).strip() if name_col else "",
                "creator_handle": str(row.get(handle_col, "")).strip() if handle_col else "",
                "content_url": str(link).strip() if link is not None else "",
                "platform": platform,
                "post_date": post_date,
                "post_description": desc,
            }
        )

    return pd.DataFrame(rows)


def merge_halo_effect_posts_and_selections(
    posted: pd.DataFrame,
    selected: pd.DataFrame,
    *,
    config: AppConfig | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Build canonical boosting content table + merge diagnostics."""
    config = config or load_config()
    if posted.empty:
        return pd.DataFrame(columns=CONTENT_RAW_COLUMNS), {"error": "posted_empty"}

    if selected.empty:
        sel = pd.DataFrame(columns=["url_key"])
    elif "url_key" in selected.columns:
        sel = selected.copy()
    else:
        sel = parse_halo_selected_csv(selected)
    sel_keys = set(sel["url_key"]) if not sel.empty else set()

    records: list[dict] = []
    matched = 0
    for _, row in posted.iterrows():
        key = row["url_key"]
        is_selected = key in sel_keys
        if is_selected:
            matched += 1
        sel_row = sel[sel["url_key"] == key].iloc[0] if is_selected and not sel.empty else None
        selection_date = sel_row["selection_date"] if sel_row is not None else pd.NaT

        pseudo = pd.Series(
            {
                "post_caption": row.get("post_description", ""),
                "post_url": row.get("content_url", ""),
            }
        )
        eligible = is_eligible_boosting_content(pseudo, config=config, api_eligible=None)
        post_date = row.get("post_date")
        month = post_date.strftime("%Y-%m") if pd.notna(post_date) else None

        records.append(
            {
                "creator_id": row["creator_id"],
                "creator_name": row.get("creator_name") or (sel_row["creator_name_selected"] if sel_row is not None else ""),
                "creator_handle": row.get("creator_handle", ""),
                "month": month,
                "content_url": row.get("content_url", ""),
                "platform": row.get("platform", ""),
                "post_date": post_date,
                "eligible": eligible,
                "selected": is_selected,
                "selection_date": selection_date,
                "boosted": False,
                "gift_card_cost": 0.0,
                "paid_spend": 0.0,
                "boosted_revenue": 0.0,
                "impressions": 0,
                "engagements": 0,
                "clicks": 0,
                "featured_category": "",
                "campaign": "Halo effect upload",
            }
        )

    content = normalize_content_raw(pd.DataFrame(records))
    diagnostics = {
        "posted_rows": len(posted),
        "selected_rows": len(sel),
        "selected_unique_assets": len(sel_keys),
        "posts_matched_to_selection": matched,
        "selection_match_rate_on_posts": matched / len(posted) if len(posted) else None,
        "eligible_posts": int(content["eligible"].sum()) if not content.empty else 0,
        "selected_posts": int(content["selected"].sum()) if not content.empty else 0,
        "selected_not_in_posted": len(sel_keys - set(posted["url_key"].unique())),
    }
    return content, diagnostics


def load_halo_effect_from_paths(posted_path: str, selected_path: str, *, config: AppConfig | None = None) -> tuple[pd.DataFrame, dict]:
    posted = parse_halo_posted_csv(posted_path)
    selected = parse_halo_selected_csv(selected_path)
    return merge_halo_effect_posts_and_selections(posted, selected, config=config)


def build_data_quality_checklist(diagnostics: dict) -> pd.DataFrame:
    """Two-column Check / Result table for Excel."""
    posted = diagnostics.get("posted_rows", 0)
    matched = diagnostics.get("posts_matched_to_selection", 0)
    rate = diagnostics.get("selection_match_rate_on_posts")
    rate_note = f"{rate * 100:.1f}% of posts" if rate is not None else ""
    not_in = diagnostics.get("selected_not_in_posted", 0)

    rows = [
        ("Posts in posted file", f"{posted:,}"),
        ("Unique selected assets in tracker", f"{diagnostics.get('selected_unique_assets', 0):,}"),
        (
            "Posts flagged selected",
            f"{diagnostics.get('selected_posts', 0):,} ({rate_note}; matches tracker on post URL)"
            if matched
            else f"{diagnostics.get('selected_posts', 0):,}",
        ),
        ("Eligible posts (both hashtags)", f"{diagnostics.get('eligible_posts', 0):,}"),
        (
            "Selected rows not in posted export",
            f"{not_in:,} — widen CreatorIQ date range or pull a longer posts export"
            if not_in
            else "0",
        ),
    ]
    return pd.DataFrame(rows, columns=["Check", "Result"])


def build_selected_not_in_posted(posted: pd.DataFrame, selected: pd.DataFrame) -> pd.DataFrame:
    """Selected tracker rows that did not match any row in the posted export."""
    if selected.empty:
        return pd.DataFrame(columns=["url_key", "content_url", "selection_date", "creator_name_selected", "platform"])
    if "url_key" not in selected.columns:
        selected = parse_halo_selected_csv(selected)
    if posted.empty or "url_key" not in posted.columns:
        posted_keys: set[str] = set()
    else:
        posted_keys = set(posted["url_key"].dropna().unique())
    missing = selected[~selected["url_key"].isin(posted_keys)].copy()
    cols = [c for c in ("url_key", "content_url", "selection_date", "creator_name_selected", "platform") if c in missing.columns]
    return missing[cols].sort_values("selection_date", na_position="last").reset_index(drop=True)


def _excel_safe_frame(df: pd.DataFrame) -> pd.DataFrame:
    """openpyxl cannot write timezone-aware datetimes."""
    if df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            series = out[col]
            if hasattr(series.dt, "tz") and series.dt.tz is not None:
                out[col] = series.dt.tz_localize(None)
    return out


def build_halo_effect_report_frames(
    posted_path: str,
    selected_path: str,
    *,
    drought_days: int = 90,
    active_days: int = 30,
    config: AppConfig | None = None,
) -> tuple[dict[str, pd.DataFrame], dict]:
    """Build named tables for Excel or Google Sheets (one CSV per table)."""
    from creatoriq_dashboard.boosting_selection_impact import (
        build_creator_selection_timeline,
        build_posting_by_days_since_last_selection,
        summarize_timeline_segments,
    )

    posted = parse_halo_posted_csv(posted_path)
    selected = parse_halo_selected_csv(selected_path)
    content, diagnostics = merge_halo_effect_posts_and_selections(posted, selected, config=config)

    checklist = build_data_quality_checklist(diagnostics)
    not_in_posted = build_selected_not_in_posted(posted, selected)
    timeline = build_creator_selection_timeline(
        content, drought_days=drought_days, active_days=active_days
    )
    segments = summarize_timeline_segments(timeline)
    buckets = build_posting_by_days_since_last_selection(
        content, active_days=active_days, bin_width_days=30, max_days=360
    )

    posts_out = content.copy()
    if not posts_out.empty:
        posts_out["eligible"] = posts_out["eligible"].map(lambda v: "Yes" if v else "No")
        posts_out["selected"] = posts_out["selected"].map(lambda v: "Yes" if v else "No")

    settings = pd.DataFrame(
        [
            ("Posted file", posted_path),
            ("Selected file", selected_path),
            ("Selection drought (days)", drought_days),
            ("Still posting window (days)", active_days),
        ],
        columns=["Setting", "Value"],
    )

    frames = {
        "data_quality": checklist,
        "settings": settings,
        "selected_not_in_posted": _excel_safe_frame(not_in_posted),
        "segment_summary": segments,
        "days_since_selection": buckets,
        "creator_timeline": _excel_safe_frame(timeline),
        "all_posts": _excel_safe_frame(posts_out),
    }
    return frames, diagnostics


# Filenames are ordered so they sort nicely in Drive / local folders.
GOOGLE_SHEETS_CSV_FILES: tuple[tuple[str, str], ...] = (
    ("data_quality", "01_data_quality.csv"),
    ("settings", "02_settings.csv"),
    ("selected_not_in_posted", "03_selected_not_in_posted.csv"),
    ("segment_summary", "04_segment_summary.csv"),
    ("days_since_selection", "05_days_since_selection.csv"),
    ("creator_timeline", "06_creator_timeline.csv"),
    ("all_posts", "07_all_posts.csv"),
)


def export_halo_effect_csv_dir(
    posted_path: str,
    selected_path: str,
    output_dir: str,
    *,
    drought_days: int = 90,
    active_days: int = 30,
    config: AppConfig | None = None,
) -> dict:
    """Write one CSV per report table — import each into a Google Sheets tab."""
    from pathlib import Path

    frames, diagnostics = build_halo_effect_report_frames(
        posted_path,
        selected_path,
        drought_days=drought_days,
        active_days=active_days,
        config=config,
    )
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for key, filename in GOOGLE_SHEETS_CSV_FILES:
        path = out_dir / filename
        frames[key].to_csv(path, index=False)
        written.append(str(path))

    readme = out_dir / "README_google_sheets.txt"
    readme.write_text(
        """Import into Google Sheets
==========================
1. Go to sheets.google.com → Blank spreadsheet.
2. For each CSV in this folder (in order 01 … 07):
   File → Import → Upload → select the CSV
   Import location: "Insert new sheet(s)" (or "Replace current sheet" for 01 only on a blank book).
3. Start with 01_data_quality.csv — that is the Check / Result table.

Tip: You can also upload the whole folder to Google Drive, then open each CSV with Google Sheets.
""",
        encoding="utf-8",
    )
    written.append(str(readme))

    diagnostics["output_dir"] = str(out_dir)
    diagnostics["csv_files"] = written
    return diagnostics


def build_halo_effect_zip_bytes(
    posted_source: str | bytes | pd.DataFrame,
    selected_source: str | bytes | pd.DataFrame,
    *,
    drought_days: int = 90,
    active_days: int = 30,
    config: AppConfig | None = None,
) -> tuple[bytes, dict]:
    """Build Google Sheets CSV bundle in memory for browser download."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        posted_path = Path(tmp) / "posted.csv"
        selected_path = Path(tmp) / "selected.csv"
        if isinstance(posted_source, pd.DataFrame):
            posted_source.to_csv(posted_path, index=False)
        elif isinstance(posted_source, bytes):
            posted_path.write_bytes(posted_source)
        else:
            posted_path.write_text(str(posted_source), encoding="utf-8")
        if isinstance(selected_source, pd.DataFrame):
            selected_source.to_csv(selected_path, index=False)
        elif isinstance(selected_source, bytes):
            selected_path.write_bytes(selected_source)
        else:
            selected_path.write_text(str(selected_source), encoding="utf-8")

        out_dir = Path(tmp) / "out"
        diagnostics = export_halo_effect_csv_dir(
            str(posted_path),
            str(selected_path),
            str(out_dir),
            drought_days=drought_days,
            active_days=active_days,
            config=config,
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(out_dir.iterdir()):
                if path.is_file():
                    zf.write(path, arcname=path.name)
        buffer.seek(0)
        return buffer.getvalue(), diagnostics


def export_halo_effect_workbook(
    posted_path: str,
    selected_path: str,
    output_path: str,
    *,
    drought_days: int = 90,
    active_days: int = 30,
    config: AppConfig | None = None,
) -> dict:
    """Write multi-sheet Excel report (data quality, timeline, analysis)."""
    frames, diagnostics = build_halo_effect_report_frames(
        posted_path,
        selected_path,
        drought_days=drought_days,
        active_days=active_days,
        config=config,
    )

    sheet_names = {
        "data_quality": "Data Quality",
        "settings": "Settings",
        "selected_not_in_posted": "Selected Not In Posted",
        "segment_summary": "Segment Summary",
        "days_since_selection": "Days Since Selection",
        "creator_timeline": "Creator Timeline",
        "all_posts": "All Posts",
    }

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for key, sheet in sheet_names.items():
            frames[key].to_excel(writer, sheet_name=sheet, index=False)

    diagnostics["output_path"] = output_path
    return diagnostics
