"""Wayfair Boosting program rules: WBP tag, campaign, and hashtag eligibility."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .config import AppConfig


def _boosting_settings(config: AppConfig) -> dict[str, Any]:
    return config.settings.get("boosting", default={}) or {}


def normalize_hashtag(tag: str) -> str:
    return str(tag).strip().lstrip("#").lower()


def text_contains_hashtag(text: str, hashtag: str) -> bool:
    """Case-insensitive match for #WayfairCreator style tags in caption text."""
    if not text or not hashtag:
        return False
    tag = re.escape(normalize_hashtag(hashtag))
    return bool(re.search(rf"(?<![\w])#?{tag}(?![\w])", str(text), flags=re.IGNORECASE))


def post_has_required_hashtags(text: str, required_hashtags: list[str]) -> bool:
    if not required_hashtags:
        return True
    return all(text_contains_hashtag(text, tag) for tag in required_hashtags)


def creator_has_boosting_tag(tags: str | None, required_tags: list[str]) -> bool:
    if not required_tags:
        return False
    if not tags or not str(tags).strip():
        return False
    haystack = str(tags)
    for tag in required_tags:
        needle = re.escape(str(tag).strip())
        if re.search(rf"\b{needle}\b", haystack, flags=re.IGNORECASE):
            return True
    return False


def wbp_creator_ids(creators: pd.DataFrame | None, config: AppConfig) -> set[str]:
    cfg = _boosting_settings(config)
    required_tags = cfg.get("creator_tags") or ["WBP"]
    if creators is None or creators.empty or "creator_id" not in creators.columns:
        return set()
    ids: set[str] = set()
    tag_col = "tags" if "tags" in creators.columns else None
    for _, row in creators.iterrows():
        cid = str(row.get("creator_id", "")).strip()
        if not cid or cid == "nan":
            continue
        if tag_col and creator_has_boosting_tag(row.get(tag_col), required_tags):
            ids.add(cid)
    return ids


def is_boosting_campaign(campaign_name: str, campaign_id: str, config: AppConfig) -> bool:
    cfg = _boosting_settings(config)
    campaign_ids = cfg.get("campaign_ids") or []
    if campaign_ids:
        return str(campaign_id) in {str(x) for x in campaign_ids}

    exact_names = cfg.get("campaign_names") or []
    if exact_names:
        name = str(campaign_name).strip().lower()
        return name in {str(n).strip().lower() for n in exact_names}

    terms = cfg.get("campaign_name_contains") or []
    if not terms:
        return False
    text = str(campaign_name).lower()
    return any(str(term).lower() in text for term in terms)


def post_text_for_eligibility(post: pd.Series) -> str:
    parts: list[str] = []
    for col in ("post_caption", "post_text", "description", "post_url"):
        val = post.get(col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        text = str(val).strip()
        if text and text.lower() not in {"nan", "none"}:
            parts.append(text)
    return " ".join(parts)


def is_boosting_creator_post(
    post: pd.Series,
    *,
    config: AppConfig,
    wbp_ids: set[str],
) -> bool:
    creator_id = str(post.get("creator_id", "")).strip()
    if creator_id in wbp_ids:
        return True
    return is_boosting_campaign(str(post.get("campaign_name", "")), str(post.get("campaign_id", "")), config)


def is_eligible_boosting_content(
    post: pd.Series,
    *,
    config: AppConfig,
    api_eligible: bool | None = None,
) -> bool:
    if api_eligible is True:
        return True
    if api_eligible is False:
        return False
    cfg = _boosting_settings(config)
    required = cfg.get("eligible_hashtags") or ["WayfairCreator", "wayfairelevate"]
    return post_has_required_hashtags(post_text_for_eligibility(post), required)
