"""October (and program) creative brief themes detected from post captions."""
from __future__ import annotations

import re

import pandas as pd

from creatoriq_dashboard.boosting_scorecard import _safe_div

# Aligns with October Boosting brief messaging buckets (caption keyword proxies).
BRIEF_THEME_PATTERNS: dict[str, str] = {
    "fall_styling": r"(?:\bfall\b|\bautumn\b|\bcozy\b|\bseasonal\b|fall decor|fall styling|fall refresh)",
    "halloween": r"\bhalloween\b",
    "holiday_preview": r"\b(?:holiday|christmas|thanksgiving|hosting|gift(?:ing)?)\b",
    "sideboard": r"\bsideboard?s?\b",
    "wayfair_verified": r"(?:wayfair\s+verified|#\s*wayfairverified\b|\bverified\s+by\s+wayfair\b)",
    "pet": r"\b(?:pet|puppy|puppies|dog|dogs|cat|cats|kitten)\b",
    "single_product_highlight": (
        r"(?:everyday upgrade|organization solution|small change|product highlight|"
        r"this (?:bed|sofa|table|chair|rug|lamp|mirror|desk|dresser|nightstand|piece)|"
        r"shop (?:this|my|the link)|link in bio|comment ['\"]shop['\"])"
    ),
}


def caption_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def text_matches_brief_theme(text: str, theme_key: str) -> bool:
    pattern = BRIEF_THEME_PATTERNS.get(theme_key)
    if not pattern or not text:
        return False
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def tag_brief_themes(text: str) -> dict[str, bool]:
    t = caption_text(text)
    return {key: text_matches_brief_theme(t, key) for key in BRIEF_THEME_PATTERNS}


def add_brief_theme_columns(df: pd.DataFrame, *, text_col: str = "post_caption") -> pd.DataFrame:
    if df.empty or text_col not in df.columns:
        out = df.copy()
        for key in BRIEF_THEME_PATTERNS:
            out[f"brief_{key}"] = False
        out["brief_any_theme"] = False
        return out
    out = df.copy()
    texts = out[text_col].map(caption_text)
    for key in BRIEF_THEME_PATTERNS:
        pattern = BRIEF_THEME_PATTERNS[key]
        out[f"brief_{key}"] = texts.str.contains(pattern, regex=True, case=False, na=False)
    theme_cols = [f"brief_{k}" for k in BRIEF_THEME_PATTERNS]
    out["brief_any_theme"] = out[theme_cols].any(axis=1)
    return out


def summarize_brief_themes_by_month(
    eligible: pd.DataFrame,
    *,
    text_col: str = "post_caption",
) -> pd.DataFrame:
    """Eligible posts only: share of posts matching each brief theme by month."""
    if eligible.empty:
        return pd.DataFrame()
    tagged = add_brief_theme_columns(eligible, text_col=text_col)
    rows: list[dict] = []
    for month, grp in tagged.groupby("month", sort=True):
        n = len(grp)
        row: dict = {"month": month, "eligible_posts": n}
        for key in BRIEF_THEME_PATTERNS:
            col = f"brief_{key}"
            hits = int(grp[col].sum())
            row[f"{key}_posts"] = hits
            row[f"{key}_pct"] = _safe_div(hits, n)
        row["any_brief_theme_posts"] = int(grp["brief_any_theme"].sum())
        row["any_brief_theme_pct"] = _safe_div(int(grp["brief_any_theme"].sum()), n)
        row["selected_posts"] = int(grp["selected"].sum()) if "selected" in grp.columns else 0
        sel = grp[grp["selected"]] if "selected" in grp.columns else grp.iloc[0:0]
        row["selected_with_brief_theme"] = int(sel["brief_any_theme"].sum()) if not sel.empty else 0
        rows.append(row)
    return pd.DataFrame(rows)


def creator_brief_alignment_in_month(
    eligible: pd.DataFrame,
    month: str,
    *,
    text_col: str = "post_caption",
) -> pd.Series:
    """Per creator_id: posted ≥1 brief-themed eligible post in ``month``."""
    sub = eligible[eligible["month"] == month]
    if sub.empty:
        return pd.Series(dtype=bool)
    tagged = add_brief_theme_columns(sub, text_col=text_col)
    return tagged.groupby("creator_id")["brief_any_theme"].any()
