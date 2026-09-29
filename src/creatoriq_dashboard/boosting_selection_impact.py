"""Selection impact: posting velocity and retention split by selection status."""
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
