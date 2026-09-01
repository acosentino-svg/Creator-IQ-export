"""Program health insight sentences from month-over-month metric changes."""
from __future__ import annotations

import pandas as pd


def _get_metric(program_long: pd.DataFrame, month: str, metric: str):
    row = program_long[(program_long["month"] == month) & (program_long["metric"] == metric)]
    if row.empty:
        return None
    val = row.iloc[0]["value"]
    return None if pd.isna(val) else float(val)


def generate_program_insights(program_long: pd.DataFrame) -> list[str]:
    if program_long.empty:
        return ["Upload monthly content data to generate program health insights."]

    months = sorted(program_long["month"].unique())
    if len(months) < 2:
        return ["Need at least two months of data for diagnostic insights."]

    curr, prev = months[-1], months[-2]
    insights: list[str] = []

    active = _get_metric(program_long, curr, "active_boosting_creators")
    active_prev = _get_metric(program_long, prev, "active_boosting_creators")
    content = _get_metric(program_long, curr, "eligible_content_pieces")
    content_prev = _get_metric(program_long, prev, "eligible_content_pieces")
    selection = _get_metric(program_long, curr, "selection_rate")
    selection_prev = _get_metric(program_long, prev, "selection_rate")
    retention = _get_metric(program_long, curr, "retention_rate")
    retention_prev = _get_metric(program_long, prev, "retention_rate")
    roas = _get_metric(program_long, curr, "roas")
    roas_prev = _get_metric(program_long, prev, "roas")

    if active and active_prev and content and content_prev and selection and selection_prev:
        if active > active_prev and content > content_prev and selection < selection_prev - 0.05:
            insights.append(
                "Creator participation increased, but the additional content is being selected at a lower rate. "
                "This may indicate that creator output is becoming less aligned with paid media needs."
            )

    if content and content_prev and retention and retention_prev:
        if content > content_prev and retention < retention_prev - 0.03:
            insights.append(
                "Content production increased this month, but fewer existing creators returned. Growth may be "
                "relying on new or reactivated creators rather than a healthy retained creator base."
            )

    if selection and selection_prev and roas and roas_prev:
        if selection > selection_prev and roas > roas_prev:
            insights.append(
                "Content quality or paid-media alignment appears to be improving. A larger share of eligible "
                "content is being selected and boosted content is generating stronger returns."
            )

    if active and active_prev and retention and retention_prev:
        if active < active_prev and retention >= retention_prev:
            insights.append(
                "The existing creator base remains relatively healthy, but new creator activation or "
                "reactivation may be slowing."
            )

    if retention and retention_prev and retention < retention_prev - 0.03:
        insights.append(
            "Creator retention declined versus the previous month. Review whether creators are receiving enough "
            "feedback, incentives, product access, or reasons to continue producing Boosting content."
        )

    return insights or ["No strong diagnostic patterns detected this month — metrics look relatively stable."]
