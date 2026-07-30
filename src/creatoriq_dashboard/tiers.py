"""Wayfair creator program tier tags (Curator, Designer, Trendsetter)."""
from __future__ import annotations

import re

PROGRAM_TIERS = ("Curator", "Designer", "Trendsetter")


def extract_tier_from_tags(tags: str | None) -> str | None:
    """Return the program tier if present in a CreatorIQ Tags / TagNames string."""
    if not tags or not str(tags).strip():
        return None
    text = str(tags)
    for tier in PROGRAM_TIERS:
        if re.search(rf"\b{re.escape(tier)}\b", text, re.I):
            return tier
    return None


def normalize_tag_string(tags: str | None) -> str:
    if not tags:
        return ""
    return str(tags).strip()
