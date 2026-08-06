"""Aggregate enrolled creator CRM location fields for geography charts."""
from __future__ import annotations

import re

import pandas as pd

_COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "ca": "Canada",
    "canada": "Canada",
    "au": "Australia",
    "australia": "Australia",
    "de": "Germany",
    "germany": "Germany",
    "fr": "France",
    "france": "France",
    "mx": "Mexico",
    "mexico": "Mexico",
    "in": "India",
    "india": "India",
    "br": "Brazil",
    "brazil": "Brazil",
}

_US_STATE_ALIASES: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
    "washington dc": "DC",
    "washington d.c.": "DC",
    "d.c.": "DC",
    "dc": "DC",
}


def _clean_text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "n/a", "na", "-"}:
        return None
    return text


def normalize_country(value: object) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    key = re.sub(r"\s+", " ", text.lower())
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    if len(key) == 2 and key.isalpha():
        return _COUNTRY_ALIASES.get(key, text.title())
    return " ".join(part.capitalize() for part in text.split())


def is_united_states(country: object) -> bool:
    normalized = normalize_country(country)
    return normalized == "United States"


def normalize_us_state(value: object) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    key = re.sub(r"\s+", " ", text.lower())
    if key in _US_STATE_ALIASES:
        return _US_STATE_ALIASES[key]
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return None


def enrich_creator_locations(creators: pd.DataFrame) -> pd.DataFrame:
    """Add normalized country/state columns used by geography charts."""
    if creators.empty:
        return creators.copy()
    out = creators.copy()
    country_src = out["country"] if "country" in out.columns else pd.Series([None] * len(out), index=out.index)
    state_src = out["state"] if "state" in out.columns else pd.Series([None] * len(out), index=out.index)
    out["country_normalized"] = country_src.map(normalize_country)
    out["state_normalized"] = state_src.map(normalize_us_state)
    return out


def location_coverage(creators: pd.DataFrame) -> dict[str, int]:
    enriched = enrich_creator_locations(creators)
    total = len(enriched)
    with_country = int(enriched["country_normalized"].notna().sum()) if total else 0
    us_mask = enriched["country_normalized"] == "United States" if total else pd.Series(dtype=bool)
    us_total = int(us_mask.sum()) if total else 0
    with_state = int(enriched.loc[us_mask, "state_normalized"].notna().sum()) if us_total else 0
    with_city = 0
    if total and "city" in enriched.columns:
        with_city = int(enriched["city"].map(_clean_text).notna().sum())
    return {
        "total": total,
        "with_country": with_country,
        "with_state_us": with_state,
        "with_city": with_city,
        "us_creators": us_total,
        "missing_country": total - with_country,
    }


def aggregate_by_country(creators: pd.DataFrame) -> pd.DataFrame:
    enriched = enrich_creator_locations(creators)
    if enriched.empty:
        return pd.DataFrame(columns=["country", "creators"])
    grouped = (
        enriched.dropna(subset=["country_normalized"])
        .groupby("country_normalized", as_index=False)
        .size()
        .rename(columns={"country_normalized": "country", "size": "creators"})
        .sort_values("creators", ascending=False)
    )
    return grouped.reset_index(drop=True)


def aggregate_by_us_state(creators: pd.DataFrame) -> pd.DataFrame:
    enriched = enrich_creator_locations(creators)
    if enriched.empty:
        return pd.DataFrame(columns=["state", "creators"])
    us = enriched[enriched["country_normalized"] == "United States"].copy()
    grouped = (
        us.dropna(subset=["state_normalized"])
        .groupby("state_normalized", as_index=False)
        .size()
        .rename(columns={"state_normalized": "state", "size": "creators"})
        .sort_values("creators", ascending=False)
    )
    return grouped.reset_index(drop=True)
