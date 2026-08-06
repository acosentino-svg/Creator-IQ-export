from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.geography import (
    aggregate_by_city,
    aggregate_by_country,
    aggregate_by_us_state,
    is_us_only_program,
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

    cov_us = location_coverage(creators, us_only_program=True)
    assert cov_us["us_creators"] == 3
    assert cov_us["us_only"] is True
    assert cov_us["missing_state_us"] == 2


def test_us_only_state_aggregation_includes_blank_country():
    creators = pd.DataFrame(
        [
            {"country": "", "state": "CA", "city": "LA"},
            {"country": "United States", "state": "TX", "city": "Dallas"},
        ]
    )
    counts = aggregate_by_us_state(creators, us_only_program=True)
    assert counts["creators"].sum() == 2
    assert set(counts["state"]) == {"CA", "TX"}


def test_is_us_only_program_detection():
    us_only = pd.DataFrame([{"country": "US", "state": "CA"}, {"country": "United States", "state": "TX"}])
    mixed = pd.DataFrame([{"country": "US", "state": "CA"}, {"country": "Canada", "state": "ON"}])
    assert is_us_only_program(us_only) is True
    assert is_us_only_program(mixed) is False
    assert is_us_only_program(mixed, us_only_program=True) is True


def test_aggregate_by_city_groups_state_and_city():
    creators = pd.DataFrame(
        [
            {"country": "US", "state": "CA", "city": "los angeles"},
            {"country": "US", "state": "CA", "city": "Los Angeles"},
            {"country": "US", "state": "TX", "city": "Dallas"},
        ]
    )
    cities = aggregate_by_city(creators, us_only_program=True)
    assert cities["creators"].sum() == 3
    assert cities.iloc[0]["creators"] == 2
    assert cities.iloc[0]["city"] == "Los Angeles"
    assert cities.iloc[0]["state"] == "CA"
