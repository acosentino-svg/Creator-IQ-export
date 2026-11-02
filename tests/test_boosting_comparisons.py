from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.boosting_comparisons import compare_months, reporting_month_pair, sorted_program_months


def _program_long(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_reporting_month_pair_skips_partial_current_month(monkeypatch):
    months = ["2026-09", "2026-10", "2026-11"]

    class FakeDatetime:
        @classmethod
        def now(cls, tz):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            return datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("America/New_York"))

    monkeypatch.setattr("creatoriq_dashboard.boosting_comparisons.datetime", FakeDatetime)
    current, previous = reporting_month_pair(months)
    assert current == "2026-10"
    assert previous == "2026-09"


def test_compare_months_uses_complete_month_and_pct():
    program = _program_long(
        [
            {"month": "2026-09", "metric": "eligible_content_pieces", "value": 661},
            {"month": "2026-10", "metric": "eligible_content_pieces", "value": 824},
            {"month": "2026-11", "metric": "eligible_content_pieces", "value": 120},
        ]
    )
    from datetime import datetime
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    fake_now = datetime(2026, 11, 2, tzinfo=ZoneInfo("America/New_York"))
    with patch("creatoriq_dashboard.boosting_comparisons.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        comp = compare_months(program, "eligible_content_pieces")

    assert comp["current"] == 824
    assert comp["previous"] == 661
    assert comp["abs_change"] == 163
    assert abs(comp["pct_change"] - (163 / 661)) < 0.001
    assert comp["skipped_partial_month"] is True


def test_sorted_program_months_not_lexicographic_trap():
    program = _program_long(
        [
            {"month": "2026-10", "metric": "eligible_content_pieces", "value": 1},
            {"month": "2026-09", "metric": "eligible_content_pieces", "value": 1},
        ]
    )
    assert sorted_program_months(program) == ["2026-09", "2026-10"]
