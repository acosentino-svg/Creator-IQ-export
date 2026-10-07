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
