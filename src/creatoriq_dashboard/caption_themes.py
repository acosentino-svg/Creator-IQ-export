"""Classify boosting / campaign post captions into marketing theme buckets.

Rules are keyword/heuristic based — tune patterns here when brief language shifts.
Posts can match multiple themes; counts are non-exclusive unless you assign a primary bucket.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

# --- Theme detectors (case-insensitive regex on caption text) ---

FALL_REFRESH = re.compile(
    r"fall\s+refresh|refresh(?:ing)?\s+for\s+fall|fall\s+(?:makeover|update|reset|revamp)",
    re.IGNORECASE,
)
FALL_GENERAL = re.compile(
    r"\bfall\b|\bautumn\b|fall\s+(?:decor|home|vibes|feeling|season|styling|mood|look|inspo|favorites|favourites)"
    r"|cozy\s+fall|fall\s+cozy|pumpkin\s+spice|sweater\s+weather",
    re.IGNORECASE,
)

HALLOWEEN = re.compile(
    r"halloween|hallowe'en|spooky\s+season|trick[\s-]?or[\s-]?treat|jack[\s-]?o[\s-]?lantern"
    r"|all\s+hallows|haunted|ghost\s+decor|witch\s+decor|\bspooky\b",
    re.IGNORECASE,
)

PRE_HOLIDAY = re.compile(
    r"pre[\s-]?holiday|holiday\s+(?:prep|ready|season|hosting|entertaining|decor|shopping)"
    r"|thanksgiving|turkey\s+day|christmas|xmas|gift\s+guide|gifting\s+season|holiday\s+gift"
    r"|black\s+friday|cyber\s+monday|way\s*days?\s+sale|wayday|hosting\s+season"
    r"|merry\s+christmas|jingle|stocking|nutcracker|winter\s+holidays|festive\s+season",
    re.IGNORECASE,
)

SIDEBOARD = re.compile(
    r"sideboard|sideboards|buffet\s+table|\bbuffet\b|credenza|media\s+console|console\s+table|entry\s+table",
    re.IGNORECASE,
)
PET = re.compile(
    r"\bpet\b|\bpets\b|\bdog\b|\bdogs\b|\bcat\b|\bcats\b|puppy|puppies|kitty|kitties|fur\s+baby"
    r"|pet[\s-]?friendly|pet\s+bed|dog\s+bed|cat\s+tree",
    re.IGNORECASE,
)
WAYFAIR_VERIFIED = re.compile(r"wayfair\s+verified|#\s*wayfairverified\b|verified\s+badge", re.IGNORECASE)

MULTI_PRODUCT = re.compile(
    r"\b(these|multiple|several|few\s+of\s+my|some\s+of\s+my|favorites|favourites|roundup|haul|"
    r"all\s+linked|everything\s+linked|shop\s+my\s+(?:room|home|favorites|space)|room\s+tour|"
    r"full\s+room|whole\s+room|makeover|before\s+and\s+after)\b",
    re.IGNORECASE,
)

FURNITURE_NOUN = re.compile(
    r"\b(sofa|sectional|rug|rugs|table|chair|chairs|lamp|bed|dresser|cabinet|cabinets|console|"
    r"sideboard|buffet|mirror|shelf|shelves|bookcase|ottoman|nightstand|headboard|vanity|desk|"
    r"bar\s+cart|chandelier|pendant|arched\s+cabinet|media\s+console)\b",
    re.IGNORECASE,
)

SINGLE_PRODUCT = re.compile(
    r"\b(this\s+(?:piece|sofa|rug|table|chair|lamp|bed|dresser|cabinet|console|sideboard|buffet|"
    r"mirror|find|item|one|arched\s+cabinet|bar\s+cart)|one\s+(?:piece|item|find)|hero\s+piece|"
    r"statement\s+piece|just\s+(?:added|got)|linked\s+(?:this|below|in\s+my\s+bio\s+for\s+this)|"
    r"(?:my|the)\s+(?:new|favorite|favourite)\s+(?:sofa|rug|table|chair|lamp|bed|dresser|"
    r"cabinet|console|sideboard|piece))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ThemeFlags:
    fall_or_fall_refresh: bool
    halloween: bool
    pre_holiday: bool
    category_sideboard: bool
    category_pet: bool
    category_wayfair_verified: bool
    category_specific: bool
    single_product_highlight: bool


def classify_caption(text: str | None) -> ThemeFlags:
    t = "" if text is None or (isinstance(text, float) and pd.isna(text)) else str(text)
    fall = bool(FALL_REFRESH.search(t) or FALL_GENERAL.search(t))
    halloween = bool(HALLOWEEN.search(t))
    pre_holiday = bool(PRE_HOLIDAY.search(t))
    sideboard = bool(SIDEBOARD.search(t))
    pet = bool(PET.search(t))
    verified = bool(WAYFAIR_VERIFIED.search(t))
    category = sideboard or pet or verified

    single = False
    if t.strip() and SINGLE_PRODUCT.search(t):
        if not MULTI_PRODUCT.search(t):
            nouns = {m.group(0).lower() for m in FURNITURE_NOUN.finditer(t)}
            if len(nouns) <= 2:
                single = True

    return ThemeFlags(
        fall_or_fall_refresh=fall,
        halloween=halloween,
        pre_holiday=pre_holiday,
        category_sideboard=sideboard,
        category_pet=pet,
        category_wayfair_verified=verified,
        category_specific=category,
        single_product_highlight=single,
    )


THEME_COLUMNS: dict[str, str] = {
    "theme_fall_or_fall_refresh": "fall_or_fall_refresh",
    "theme_halloween": "halloween",
    "theme_pre_holiday": "pre_holiday",
    "theme_category_sideboard": "category_sideboard",
    "theme_category_pet": "category_pet",
    "theme_category_wayfair_verified": "category_wayfair_verified",
    "theme_category_specific": "category_specific",
    "theme_single_product_highlight": "single_product_highlight",
}


def add_theme_columns(df: pd.DataFrame, caption_col: str = "post_caption") -> pd.DataFrame:
    if caption_col not in df.columns:
        raise ValueError(f"Missing caption column: {caption_col}")
    out = df.copy()
    flags = out[caption_col].apply(classify_caption)
    for col, attr in THEME_COLUMNS.items():
        out[col] = [getattr(f, attr) for f in flags]
    return out


def theme_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Row counts per theme column (non-exclusive)."""
    rows = []
    for col in THEME_COLUMNS:
        if col not in df.columns:
            continue
        rows.append({"theme": col.replace("theme_", ""), "post_count": int(df[col].sum())})
    return pd.DataFrame(rows)


def assign_primary_theme(row: pd.Series) -> str:
    """Mutually exclusive bucket for reporting (priority order)."""
    order = [
        ("halloween", "theme_halloween"),
        ("pre_holiday", "theme_pre_holiday"),
        ("fall_or_fall_refresh", "theme_fall_or_fall_refresh"),
        ("category_specific", "theme_category_specific"),
        ("single_product_highlight", "theme_single_product_highlight"),
    ]
    for label, col in order:
        if row.get(col):
            return label
    return "other"
