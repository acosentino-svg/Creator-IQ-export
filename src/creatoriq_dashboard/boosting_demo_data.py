"""Synthetic Boosting program content for demo / exploration."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .boosting_scorecard import CONTENT_RAW_COLUMNS, normalize_content_raw

PLATFORMS = ["TikTok", "Instagram", "YouTube", "Pinterest"]
CATEGORIES = ["Bedding", "Living Room", "Kitchen", "Outdoor", "Office"]
CAMPAIGNS = ["Always-on", "Fall Refresh", "Way Day", "Spring Launch"]


def generate_demo_boosting_content(
    *,
    seed: int = 42,
    months: tuple[str, ...] = ("2026-05", "2026-06", "2026-07", "2026-08"),
    n_creators: int = 120,
) -> pd.DataFrame:
    """Generate realistic multi-month boosting content with retention dynamics."""
    rng = np.random.default_rng(seed)
    creator_ids = [f"pub_{i:04d}" for i in range(1, n_creators + 1)]

    # Each creator has a participation profile
    profiles = {
        cid: {
            "join_month_idx": int(rng.integers(0, len(months))),
            "activity_rate": float(rng.uniform(0.15, 0.95)),
            "selection_rate": float(rng.uniform(0.05, 0.75)),
            "churn_after": int(rng.integers(1, len(months) + 2)),
        }
        for cid in creator_ids
    }

    rows: list[dict] = []
    content_idx = 0

    for month_idx, month in enumerate(months):
        for cid in creator_ids:
            profile = profiles[cid]
            if month_idx < profile["join_month_idx"]:
                continue
            if month_idx - profile["join_month_idx"] >= profile["churn_after"] and rng.random() < 0.55:
                continue
            if rng.random() > profile["activity_rate"]:
                continue

            n_pieces = int(rng.integers(1, 6))
            for _ in range(n_pieces):
                content_idx += 1
                eligible = True
                selected = eligible and rng.random() < profile["selection_rate"]
                boosted = selected and rng.random() < 0.85
                gift_card = rng.choice([50.0, 100.0, 100.0, 150.0]) if selected else 0.0
                paid_spend = float(rng.uniform(80, 600)) if boosted else 0.0
                roas_factor = float(rng.uniform(1.2, 5.5)) if boosted else 0.0
                revenue = paid_spend * roas_factor if boosted else 0.0

                post_day = int(rng.integers(1, 27))
                post_date = pd.Timestamp(f"{month}-{post_day:02d}", tz="UTC")

                rows.append(
                    {
                        "creator_id": cid,
                        "month": month,
                        "content_url": f"https://example.com/content/{content_idx}",
                        "platform": rng.choice(PLATFORMS),
                        "post_date": post_date,
                        "eligible": eligible,
                        "selected": selected,
                        "selection_date": post_date + pd.Timedelta(days=int(rng.integers(2, 10))) if selected else pd.NaT,
                        "boosted": boosted,
                        "gift_card_cost": gift_card,
                        "paid_spend": round(paid_spend, 2),
                        "boosted_revenue": round(revenue, 2),
                        "impressions": int(rng.integers(5_000, 250_000)) if boosted else 0,
                        "engagements": int(rng.integers(200, 15_000)) if boosted else 0,
                        "clicks": int(rng.integers(50, 8_000)) if boosted else 0,
                        "featured_category": rng.choice(CATEGORIES),
                        "campaign": rng.choice(CAMPAIGNS),
                    }
                )

    df = pd.DataFrame(rows, columns=CONTENT_RAW_COLUMNS)
    return normalize_content_raw(df)
