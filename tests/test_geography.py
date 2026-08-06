from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.geography import (
    aggregate_by_country,
    aggregate_by_us_state,
    location_coverage,
    normalize_country,
    normalize_us_state,
)


def test_normalize_country_aliases():
    assert normalize_country("US") == "United States"
    assert normalize_country("united kingdom") == "United Kingdom"
    assert normalize_country("  Canada ") == "Canada"


def test_normalize_us_state():
    assert normalize_us_state("California") == "CA"
    assert normalize_us_state("tx") == "TX"
    assert normalize_us_state("New York") == "NY"


def test_aggregate_by_country_and_state():
    creators = pd.DataFrame(
        [
            {"country": "US", "state": "CA", "city": "Los Angeles"},
            {"country": "United States", "state": "Texas", "city": "Dallas"},
            {"country": "Canada", "state": "ON", "city": "Toronto"},
            {"country": "", "state": "", "city": ""},
        ]
    )
    country_counts = aggregate_by_country(creators)
    assert country_counts["creators"].sum() == 3
    assert country_counts.iloc[0]["country"] == "United States"
    assert country_counts.iloc[0]["creators"] == 2

    state_counts = aggregate_by_us_state(creators)
    assert state_counts["creators"].sum() == 2
    assert set(state_counts["state"]) == {"CA", "TX"}


def test_location_coverage():
    creators = pd.DataFrame(
        [
            {"country": "US", "state": "CA", "city": "LA"},
            {"country": "US", "state": "", "city": ""},
            {"country": "", "state": "", "city": ""},
        ]
    )
    cov = location_coverage(creators)
    assert cov["total"] == 3
    assert cov["with_country"] == 2
    assert cov["us_creators"] == 2
    assert cov["with_state_us"] == 1
    assert cov["with_city"] == 1
