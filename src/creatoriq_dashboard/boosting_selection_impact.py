"""Selection impact: posting velocity and retention split by selection status.

Day-level views use ``post_date`` and ``selection_date`` (when present), not calendar
month buckets — so you can see creators who stopped getting selected months ago and
then stopped posting.
"""
from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.boosting_scorecard import (
    _active_creators_by_month,
    _eligible_content,
    _month_period,
    _prior_month,
    _safe_div,
    build_creator_monthly,
    build_program_monthly,
    normalize_content_raw,
)


def _as_of_timestamp(eligible: pd.DataFrame, as_of: pd.Timestamp | None) -> pd.Timestamp:
    if as_of is not None and pd.notna(as_of):
        return pd.Timestamp(as_of).tz_convert("UTC") if pd.Timestamp(as_of).tzinfo else pd.Timestamp(as_of, tz="UTC")
    if eligible.empty or eligible["post_date"].isna().all():
        return pd.Timestamp.now(tz="UTC")
    return pd.Timestamp(eligible["post_date"].max()).tz_convert("UTC")


def _creator_last_selection_date(sel_rows: pd.DataFrame) -> pd.Timestamp | None:
    if sel_rows.empty:
        return None
    dates = sel_rows["selection_date"].dropna()
    if not dates.empty:
        return pd.Timestamp(dates.max()).tz_convert("UTC")
    post_dates = sel_rows["post_date"].dropna()
    if post_dates.empty:
        return None
    return pd.Timestamp(post_dates.max()).tz_convert("UTC")


def build_creator_selection_timeline(
    content: pd.DataFrame,
    *,
    as_of: pd.Timestamp | None = None,
    drought_days: int = 90,
    active_days: int = 30,
) -> pd.DataFrame:
    """One row per creator: selection history and whether they still post (day-based).

    Segments (mutually exclusive):
    - **Never selected** — no selected eligible content on record
    - **Recently selected** — last selection within ``drought_days`` of ``as_of``
    - **Past selector — still posting** — last selection older than drought, but posted within ``active_days``
    - **Past selector — went dark** — last selection older than drought, no eligible post in ``active_days``
    """
    eligible = _eligible_content(normalize_content_raw(content))
    columns = [
        "creator_id",
        "creator_name",
        "first_selection_date",
        "last_selection_date",
        "last_eligible_post_date",
        "days_since_last_selection",
        "days_since_last_post",
        "eligible_posts",
        "selected_posts",
        "posted_in_last_n_days",
        "segment",
    ]
    if eligible.empty:
        return pd.DataFrame(columns=columns)

    as_of_ts = _as_of_timestamp(eligible, as_of)
    drought = pd.Timedelta(days=drought_days)
    active = pd.Timedelta(days=active_days)

    rows: list[dict] = []
    for creator_id, grp in eligible.groupby("creator_id"):
        name = ""
        if "creator_name" in grp.columns:
            name = next((str(v) for v in grp["creator_name"] if str(v).strip() not in {"", "nan"}), "")

        sel_rows = grp[grp["selected"]]
        selected_posts = int(len(sel_rows))
        eligible_posts = int(len(grp))

        last_post = grp["post_date"].dropna()
        last_post_ts = pd.Timestamp(last_post.max()).tz_convert("UTC") if not last_post.empty else None

        if selected_posts == 0:
            posted_recently = last_post_ts is not None and (as_of_ts - last_post_ts) <= active
            segment = "Never selected — still posting" if posted_recently else "Never selected — went dark"
            rows.append(
                {
                    "creator_id": creator_id,
                    "creator_name": name,
                    "first_selection_date": None,
                    "last_selection_date": None,
                    "last_eligible_post_date": last_post_ts,
                    "days_since_last_selection": None,
                    "days_since_last_post": (as_of_ts - last_post_ts).days if last_post_ts else None,
                    "eligible_posts": eligible_posts,
                    "selected_posts": 0,
                    "posted_in_last_n_days": posted_recently,
                    "segment": segment,
                }
            )
            continue

        first_dates = []
        for _, row in sel_rows.iterrows():
            d = row["selection_date"]
            if pd.notna(d):
                first_dates.append(pd.Timestamp(d).tz_convert("UTC"))
            elif pd.notna(row["post_date"]):
                first_dates.append(pd.Timestamp(row["post_date"]).tz_convert("UTC"))
        first_sel_ts = min(first_dates) if first_dates else None
        last_sel_ts = _creator_last_selection_date(sel_rows)

        days_since_sel = (as_of_ts - last_sel_ts).days if last_sel_ts else None
        days_since_post = (as_of_ts - last_post_ts).days if last_post_ts else None
        posted_recently = last_post_ts is not None and (as_of_ts - last_post_ts) <= active

        if last_sel_ts and (as_of_ts - last_sel_ts) <= drought:
            segment = "Recently selected"
        elif posted_recently:
            segment = "Past selector — still posting"
        else:
            segment = "Past selector — went dark"

        rows.append(
            {
                "creator_id": creator_id,
                "creator_name": name,
                "first_selection_date": first_sel_ts,
                "last_selection_date": last_sel_ts,
                "last_eligible_post_date": last_post_ts,
                "days_since_last_selection": days_since_sel,
                "days_since_last_post": days_since_post,
                "eligible_posts": eligible_posts,
                "selected_posts": selected_posts,
                "posted_in_last_n_days": posted_recently,
                "segment": segment,
            }
        )

    return pd.DataFrame(rows).sort_values(["segment", "days_since_last_selection"], na_position="last")


def summarize_timeline_segments(timeline: pd.DataFrame) -> pd.DataFrame:
    """Counts and % still posting within each segment."""
    if timeline.empty:
        return pd.DataFrame(columns=["segment", "creators", "still_posting", "pct_still_posting"])
    grouped = timeline.groupby("segment", sort=False)
    rows = []
    for segment, grp in grouped:
        still = int(grp["posted_in_last_n_days"].sum())
        rows.append(
            {
                "segment": segment,
                "creators": len(grp),
                "still_posting": still,
                "pct_still_posting": _safe_div(still, len(grp)),
            }
        )
    return pd.DataFrame(rows)


def build_posting_by_days_since_last_selection(
    content: pd.DataFrame,
    *,
    as_of: pd.Timestamp | None = None,
    active_days: int = 30,
    bin_width_days: int = 30,
    max_days: int = 360,
) -> pd.DataFrame:
    """Among creators who were ever selected, bucket by days since last selection.

    For each bucket: how many creators and what % posted at least once in the last
    ``active_days`` (relative to ``as_of``). This surfaces long-run falloff after
    selections stop — not month-over-month noise.
    """
    timeline = build_creator_selection_timeline(content, as_of=as_of, drought_days=0, active_days=active_days)
    selected = timeline[timeline["last_selection_date"].notna()].copy()
    if selected.empty:
        return pd.DataFrame(
            columns=[
                "days_since_last_selection_bucket",
                "bucket_start_days",
                "creators",
                "still_posting",
                "pct_still_posting",
            ]
        )

    selected = selected[selected["days_since_last_selection"].notna()]
    selected["bucket_start_days"] = (
        (selected["days_since_last_selection"] // bin_width_days) * bin_width_days
    ).astype(int)
    selected = selected[selected["bucket_start_days"] <= max_days]

    rows: list[dict] = []
    for start, grp in selected.groupby("bucket_start_days"):
        end = start + bin_width_days - 1
        still = int(grp["posted_in_last_n_days"].sum())
        rows.append(
            {
                "days_since_last_selection_bucket": f"{start}–{end} days",
                "bucket_start_days": start,
                "creators": len(grp),
                "still_posting": still,
                "pct_still_posting": _safe_div(still, len(grp)),
            }
        )
    return pd.DataFrame(rows).sort_values("bucket_start_days")


def build_monthly_selection_retention(content: pd.DataFrame) -> pd.DataFrame:
    """Month-over-month retention split by whether the creator had a selection last month.

    Answers: among creators who posted eligible content last month, what share come back
    this month — and how does that differ if they were selected vs not?
    """
    eligible = _eligible_content(normalize_content_raw(content))
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "month",
                "segment",
                "prior_month_creators",
                "retained",
                "lapsed",
                "retention_rate",
                "falloff_rate",
            ]
        )

    creator_monthly = build_creator_monthly(content)
    active_by_month = _active_creators_by_month(eligible)
    months = sorted(eligible["month"].unique())

    rows: list[dict] = []
    for month in months:
        prior = _prior_month(month)
        prior_active = active_by_month.get(prior)
        if not prior_active:
            continue

        current_active = active_by_month.get(month, set())
        prior_lookup = creator_monthly[creator_monthly["month"] == prior].set_index("creator_id")

        segments = {
            "Had selection last month": {
                cid
                for cid in prior_active
                if cid in prior_lookup.index and int(prior_lookup.loc[cid, "selected_pieces"]) > 0
            },
            "No selection last month": {
                cid
                for cid in prior_active
                if cid not in prior_lookup.index or int(prior_lookup.loc[cid, "selected_pieces"]) == 0
            },
        }

        for segment, cohort in segments.items():
            if not cohort:
                continue
            retained = len(cohort & current_active)
            lapsed = len(cohort) - retained
            rows.append(
                {
                    "month": month,
                    "segment": segment,
                    "prior_month_creators": len(cohort),
                    "retained": retained,
                    "lapsed": lapsed,
                    "retention_rate": _safe_div(retained, len(cohort)),
                    "falloff_rate": _safe_div(lapsed, len(cohort)),
                }
            )

    return pd.DataFrame(rows)


def build_creator_posting_velocity(content: pd.DataFrame) -> pd.DataFrame:
    """Per-creator average eligible pieces/month before vs after first selection month."""
    creator_monthly = build_creator_monthly(content)
    if creator_monthly.empty:
        return pd.DataFrame(
            columns=[
                "creator_id",
                "creator_name",
                "first_selection_month",
                "pre_active_months",
                "post_active_months",
                "pre_avg_eligible_pieces",
                "post_avg_eligible_pieces",
                "post_minus_pre",
                "ever_selected",
            ]
        )

    rows: list[dict] = []
    for creator_id, grp in creator_monthly.groupby("creator_id"):
        grp = grp.sort_values("month")
        name = str(grp["creator_name"].iloc[0]) if "creator_name" in grp.columns else ""
        selected = grp[grp["selected_pieces"] > 0]
        if selected.empty:
            rows.append(
                {
                    "creator_id": creator_id,
                    "creator_name": name,
                    "first_selection_month": None,
                    "pre_active_months": len(grp),
                    "post_active_months": 0,
                    "pre_avg_eligible_pieces": float(grp["eligible_pieces"].mean()),
                    "post_avg_eligible_pieces": None,
                    "post_minus_pre": None,
                    "ever_selected": False,
                }
            )
            continue

        first_sel = str(selected.iloc[0]["month"])
        first_period = _month_period(first_sel)
        pre = grp[grp["month"].map(lambda m: _month_period(str(m)) < first_period)]
        post = grp[grp["month"].map(lambda m: _month_period(str(m)) > first_period)]

        pre_avg = float(pre["eligible_pieces"].mean()) if len(pre) else None
        post_avg = float(post["eligible_pieces"].mean()) if len(post) else None
        delta = None
        if pre_avg is not None and post_avg is not None:
            delta = post_avg - pre_avg

        rows.append(
            {
                "creator_id": creator_id,
                "creator_name": name,
                "first_selection_month": first_sel,
                "pre_active_months": len(pre),
                "post_active_months": len(post),
                "pre_avg_eligible_pieces": pre_avg,
                "post_avg_eligible_pieces": post_avg,
                "post_minus_pre": delta,
                "ever_selected": True,
            }
        )

    return pd.DataFrame(rows)


def summarize_selection_impact(content: pd.DataFrame) -> dict:
    """Program-level summary for dashboards and exports."""
    program = build_program_monthly(content)
    retention_split = build_monthly_selection_retention(content)
    velocity = build_creator_posting_velocity(content)

    latest_month = None
    pct_active_selected = None
    if not program.empty:
        latest_month = max(program["month"].unique(), key=lambda m: _month_period(str(m)))
        row = program[(program["month"] == latest_month) & (program["metric"] == "pct_active_creators_selected")]
        if not row.empty and pd.notna(row.iloc[0]["value"]):
            pct_active_selected = float(row.iloc[0]["value"])

    paired = velocity[velocity["post_minus_pre"].notna()]
    avg_lift = float(paired["post_minus_pre"].mean()) if not paired.empty else None
    median_lift = float(paired["post_minus_pre"].median()) if not paired.empty else None
    share_increased = _safe_div(int((paired["post_minus_pre"] > 0).sum()), len(paired)) if not paired.empty else None

    never = velocity[~velocity["ever_selected"]]
    never_avg = float(never["pre_avg_eligible_pieces"].mean()) if not never.empty else None

    selected_post = velocity[velocity["ever_selected"] & velocity["post_avg_eligible_pieces"].notna()]
    selected_post_avg = float(selected_post["post_avg_eligible_pieces"].mean()) if not selected_post.empty else None

    latest_split = retention_split[retention_split["month"] == latest_month] if latest_month else retention_split.iloc[0:0]
    falloff_no_selection = None
    retention_with_selection = None
    if not latest_split.empty:
        no_sel = latest_split[latest_split["segment"] == "No selection last month"]
        with_sel = latest_split[latest_split["segment"] == "Had selection last month"]
        if not no_sel.empty and pd.notna(no_sel.iloc[0]["falloff_rate"]):
            falloff_no_selection = float(no_sel.iloc[0]["falloff_rate"])
        if not with_sel.empty and pd.notna(with_sel.iloc[0]["retention_rate"]):
            retention_with_selection = float(with_sel.iloc[0]["retention_rate"])

    return {
        "latest_month": latest_month,
        "pct_active_creators_selected": pct_active_selected,
        "creators_with_pre_and_post_selection": int(len(paired)),
        "avg_eligible_pieces_lift_after_selection": avg_lift,
        "median_eligible_pieces_lift_after_selection": median_lift,
        "share_of_selected_creators_posting_more_after": share_increased,
        "avg_eligible_pieces_never_selected": never_avg,
        "avg_eligible_pieces_after_first_selection": selected_post_avg,
        "falloff_rate_no_selection_prior_month": falloff_no_selection,
        "retention_rate_had_selection_prior_month": retention_with_selection,
    }


def _period_bounds(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    if end_ts == end_ts.normalize():
        end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return start_ts, end_ts


def summarize_eligible_period(
    content: pd.DataFrame,
    *,
    period_label: str,
    start: str,
    end: str,
    as_of: str | None = None,
    active_days: int = 30,
    drought_days: int = 90,
) -> dict:
    """Eligible-post activity and selection rates for one calendar window."""
    from creatoriq_dashboard.boosting_halo_effect import filter_content_by_post_dates

    start_ts, end_ts = _period_bounds(start, end)
    as_of_ts = pd.Timestamp(as_of or end, tz="UTC")
    if as_of_ts == as_of_ts.normalize():
        as_of_ts = as_of_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    window = filter_content_by_post_dates(content, start=start_ts, end=end_ts)
    eligible = _eligible_content(normalize_content_raw(window))
    if eligible.empty:
        return {
            "period": period_label,
            "start": start,
            "end": end,
            "eligible_posts": 0,
            "selected_eligible_posts": 0,
            "post_selection_rate": None,
            "active_creators": 0,
            "creators_with_selected_post": 0,
            "creator_selection_rate": None,
            "avg_eligible_posts_per_active_creator": None,
            "pct_active_still_posting_at_as_of": None,
            "creators_went_dark_at_as_of": 0,
        }

    eligible_posts = len(eligible)
    selected_posts = int(eligible["selected"].sum())
    active = eligible["creator_id"].nunique()
    creators_selected = eligible.loc[eligible["selected"], "creator_id"].nunique()

    # Retention among creators active in this window: posted within active_days before as_of
    active_window = pd.Timedelta(days=active_days)
    still = 0
    dark = 0
    for _, grp in eligible.groupby("creator_id"):
        last_post = grp["post_date"].dropna()
        if last_post.empty:
            dark += 1
            continue
        last_ts = pd.Timestamp(last_post.max()).tz_convert("UTC")
        if (as_of_ts - last_ts) <= active_window:
            still += 1
        else:
            dark += 1

    return {
        "period": period_label,
        "start": start,
        "end": end,
        "eligible_posts": eligible_posts,
        "selected_eligible_posts": selected_posts,
        "post_selection_rate": _safe_div(selected_posts, eligible_posts),
        "active_creators": active,
        "creators_with_selected_post": creators_selected,
        "creator_selection_rate": _safe_div(creators_selected, active),
        "avg_eligible_posts_per_active_creator": _safe_div(eligible_posts, active),
        "pct_active_still_posting_at_as_of": _safe_div(still, active),
        "creators_still_posting_at_as_of": still,
        "creators_went_dark_at_as_of": dark,
    }


def summarize_tracker_selections_in_period(
    selected: pd.DataFrame,
    *,
    period_label: str,
    start: str,
    end: str,
) -> dict:
    """Boosting picks recorded in column D (Duration of Usage) inside the window."""
    if selected.empty or "selection_date" not in selected.columns:
        return {
            "period": period_label,
            "selections_in_period": 0,
            "unique_assets": 0,
            "unique_creators": 0,
        }
    start_ts, end_ts = _period_bounds(start, end)
    dates = pd.to_datetime(selected["selection_date"], utc=True, errors="coerce")
    mask = (dates >= start_ts) & (dates <= end_ts)
    in_period = selected.loc[mask]
    creators = in_period["creator_name_selected"].dropna().astype(str).str.strip()
    creators = creators[creators.ne("") & creators.ne("nan")]
    return {
        "period": period_label,
        "selections_in_period": int(len(in_period)),
        "unique_assets": int(in_period["url_key"].nunique()) if "url_key" in in_period.columns else len(in_period),
        "unique_creators": int(creators.nunique()) if not creators.empty else 0,
    }


def build_huddle_oct_vs_jul_sep(
    content: pd.DataFrame,
    selected: pd.DataFrame,
    *,
    active_days: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    """Compare Jul–Sep vs Oct for huddle: KPI table, monthly trend, cohort handoff, talking points."""
    from creatoriq_dashboard.boosting_halo_effect import filter_content_by_post_dates

    jul_sep = summarize_eligible_period(
        content,
        period_label="Jul–Sep 2026",
        start="2026-07-01",
        end="2026-09-30",
        as_of="2026-09-30",
        active_days=active_days,
    )
    october = summarize_eligible_period(
        content,
        period_label="Oct 2026",
        start="2026-10-01",
        end="2026-10-31",
        as_of="2026-10-31",
        active_days=active_days,
    )
    tr_jul_sep = summarize_tracker_selections_in_period(
        selected, period_label="Jul–Sep 2026", start="2026-07-01", end="2026-09-30"
    )
    tr_oct = summarize_tracker_selections_in_period(
        selected, period_label="Oct 2026", start="2026-10-01", end="2026-10-31"
    )

    def _merge_period_row(eligible_summary: dict, tracker_summary: dict) -> dict:
        row = dict(eligible_summary)
        for key, value in tracker_summary.items():
            if key == "period":
                continue
            row[f"tracker_{key}"] = value
        return row

    period_df = pd.DataFrame(
        [
            _merge_period_row(jul_sep, tr_jul_sep),
            _merge_period_row(october, tr_oct),
        ]
    )

    program = build_program_monthly(content)
    months_keep = {"2026-07", "2026-08", "2026-09", "2026-10"}
    monthly = program[program["month"].isin(months_keep)].copy()
    monthly_pivot = monthly.pivot(index="month", columns="metric", values="value").reset_index()

    def _month_rate(m: str) -> float | None:
        row = monthly_pivot[monthly_pivot["month"] == m]
        if row.empty or "selection_rate" not in row.columns:
            return None
        val = row.iloc[0]["selection_rate"]
        return float(val) if pd.notna(val) else None

    # Jul–Sep active cohort → October behavior
    js_start, js_end = _period_bounds("2026-07-01", "2026-09-30")
    oct_start, oct_end = _period_bounds("2026-10-01", "2026-10-31")
    eligible_all = _eligible_content(normalize_content_raw(content))
    js_posts = eligible_all[(eligible_all["post_date"] >= js_start) & (eligible_all["post_date"] <= js_end)]
    cohort = set(js_posts["creator_id"].unique())
    oct_posts = eligible_all[(eligible_all["post_date"] >= oct_start) & (eligible_all["post_date"] <= oct_end)]
    oct_active = set(oct_posts["creator_id"].unique())
    posted_oct = len(cohort & oct_active)
    lapsed = len(cohort - oct_active)

    js_sel = js_posts[js_posts["selected"]]["creator_id"].nunique()
    cohort_oct_eligible = oct_posts[oct_posts["creator_id"].isin(cohort)]
    cohort_oct_selected = (
        int(cohort_oct_eligible[cohort_oct_eligible["selected"]]["creator_id"].nunique())
        if not cohort_oct_eligible.empty
        else 0
    )

    cohort_df = pd.DataFrame(
        [
            {"metric": "Creators with eligible posts Jul–Sep", "value": len(cohort)},
            {"metric": "Of those, posted eligible again in Oct", "value": posted_oct},
            {"metric": "Of those, no eligible post in Oct (lapsed)", "value": lapsed},
            {"metric": "Oct continuation rate", "value": _safe_div(posted_oct, len(cohort))},
            {"metric": "Jul–Sep cohort: had selected post Jul–Sep", "value": js_sel},
            {"metric": "Jul–Sep cohort: selected eligible post in Oct", "value": cohort_oct_selected},
        ]
    )

    through_sep = filter_content_by_post_dates(content, end="2026-09-30")
    through_oct = filter_content_by_post_dates(content, end="2026-10-31")
    seg_sep = summarize_timeline_segments(
        build_creator_selection_timeline(
            through_sep, as_of="2026-09-30", active_days=active_days, drought_days=90
        )
    )
    seg_oct = summarize_timeline_segments(
        build_creator_selection_timeline(
            through_oct, as_of="2026-10-31", active_days=active_days, drought_days=90
        )
    )
    seg_sep["as_of"] = "2026-09-30"
    seg_oct["as_of"] = "2026-10-31"
    segment_df = pd.concat([seg_sep, seg_oct], ignore_index=True)

    def _pct(x):
        return f"{x * 100:.1f}%" if x is not None and pd.notna(x) else "—"

    def _delta(a, b):
        if a is None or b is None or pd.isna(a) or pd.isna(b):
            return None
        return b - a

    post_rate_js = jul_sep["post_selection_rate"]
    post_rate_oct = october["post_selection_rate"]
    creator_rate_js = jul_sep["creator_selection_rate"]
    creator_rate_oct = october["creator_selection_rate"]

    never_dark_sep = int(seg_sep.loc[seg_sep["segment"] == "Never selected — went dark", "creators"].iloc[0])
    never_still_sep = int(seg_sep.loc[seg_sep["segment"] == "Never selected — still posting", "creators"].iloc[0])
    never_dark_oct = int(seg_oct.loc[seg_oct["segment"] == "Never selected — went dark", "creators"].iloc[0])
    never_still_oct = int(seg_oct.loc[seg_oct["segment"] == "Never selected — still posting", "creators"].iloc[0])

    bullets = [
        f"Eligible volume: {jul_sep['eligible_posts']:,} posts (Jul–Sep) → {october['eligible_posts']:,} in Oct ({october['active_creators']} active creators vs {jul_sep['active_creators']} over Jul–Sep).",
        f"Post-level selection rate (#WayfairCreator + #wayfairelevate): {_pct(post_rate_js)} → {_pct(post_rate_oct)} ({_pct(_delta(post_rate_js, post_rate_oct))} pts).",
        f"Share of active creators with ≥1 selected eligible post in-window: {_pct(creator_rate_js)} → {_pct(creator_rate_oct)}.",
        f"Tracker picks (column D): {tr_jul_sep['unique_assets']} assets Jul–Sep (~{tr_jul_sep['unique_assets']/3:.0f}/mo) vs {tr_oct['unique_assets']} in Oct; {tr_oct['unique_creators']} creators in Oct tracker.",
        f"CreatorIQ match: only {october['selected_eligible_posts']} eligible posts in Oct flagged selected vs {tr_oct['unique_assets']} tracker rows — check URL/date alignment for the gap.",
        f"Jul–Sep active cohort ({len(cohort)} creators): {_pct(_safe_div(posted_oct, len(cohort)))} posted eligible again in Oct; {lapsed} no eligible Oct post.",
        f"Monthly post selection rate: Jul {_pct(_month_rate('2026-07'))} → Aug {_pct(_month_rate('2026-08'))} → Sep {_pct(_month_rate('2026-09'))} → Oct {_pct(post_rate_oct)} (eligible posts only).",
        f"Never-selected: {never_still_sep} still posting vs {never_dark_sep} dark (Sep 30); {never_still_oct} still posting vs {never_dark_oct} dark (Oct 31) — 30d window, full program history through each date.",
        "Frame for huddle: brief + higher boosting should show up in tracker pace and Oct eligible volume; selection *match rate on CreatorIQ posts* is lagging tracker — worth Ellie/Bella sync on URLs and timing.",
    ]

    return period_df, monthly_pivot, cohort_df, segment_df, bullets
