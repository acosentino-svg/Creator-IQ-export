from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.creator_geography_upload import (
    merge_geography_creator_frames,
    merge_geography_into_creators,
    parse_creator_geography_csv,
)


def test_parse_creator_geography_csv_detects_columns():
    raw = pd.DataFrame(
        {
            "Publisher Id": ["1", "2"],
            "Publisher Name": ["Ava", "Liam"],
            "State": ["CA", "TX"],
            "City": ["Los Angeles", "Dallas"],
            "Country": ["US", "US"],
        }
    )
    parsed = parse_creator_geography_csv(raw)
    assert len(parsed) == 2
    assert parsed.iloc[0]["state"] == "CA"
    assert parsed.iloc[0]["city"] == "Los Angeles"


def test_merge_partial_uploads():
    first = parse_creator_geography_csv(
        pd.DataFrame({"Publisher Id": ["1"], "State": ["CA"], "City": ["LA"]})
    )
    second = parse_creator_geography_csv(
        pd.DataFrame({"Publisher Id": ["2"], "State": ["TX"], "City": ["Dallas"]})
    )
    merged = merge_geography_creator_frames(first, second)
    assert len(merged) == 2


def test_merge_geography_into_creators():
    creators = pd.DataFrame({"creator_id": ["1"], "name": ["Old"], "state": "", "city": ""})
    geo = pd.DataFrame({"creator_id": ["1"], "name": ["Ava"], "country": "US", "state": "CA", "city": "LA"})
    out = merge_geography_into_creators(creators, geo)
    assert out.iloc[0]["state"] == "CA"
    assert out.iloc[0]["city"] == "LA"
