"""Synthetic CreatorIQ-shaped data so the dashboard is fully explorable
without live API credentials. Useful for local development, demos, and
tests. Set CREATORIQ_DASHBOARD_MODE=demo (the default) to use this.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TIERS = ["VIP", "Core", "Emerging", "New"]
PLATFORMS = ["Instagram", "TikTok", "YouTube", "Pinterest"]
POST_TYPES = ["Reel", "Static Post", "Story", "Video"]


@dataclass
class DemoData:
    creators: pd.DataFrame
    campaigns: pd.DataFrame
    posts: pd.DataFrame
    links: pd.DataFrame
    email_events: pd.DataFrame


def generate_demo_data(n_creators: int = 180, days_of_history: int = 120, seed: int = 42) -> DemoData:
    rng = np.random.default_rng(seed)
    now = pd.Timestamp.now(tz="UTC")

    # --- Creators ---
    creator_ids = [f"cr_{i:04d}" for i in range(n_creators)]
    joined_offsets = rng.integers(30, 730, size=n_creators)
    tiers = rng.choice(TIERS, size=n_creators, p=[0.08, 0.27, 0.35, 0.30])
    # Behavioral archetype drives how often a creator posts/opens email, so
    # segments in the dashboard actually look realistic.
    archetypes = rng.choice(
        ["superfan", "steady", "fading", "ghost", "new_never_started"],
        size=n_creators,
        p=[0.12, 0.33, 0.20, 0.20, 0.15],
    )
    creators = pd.DataFrame(
        {
            "creator_id": creator_ids,
            "name": [f"Creator {i:04d}" for i in range(n_creators)],
            "email": [f"creator{i:04d}@example.com" for i in range(n_creators)],
            "status": "Active",
            "tier": tiers,
            "joined_date": [now - pd.Timedelta(days=int(o)) for o in joined_offsets],
            "_archetype": archetypes,
        }
    )

    # --- Campaigns ---
    campaign_names = [
        "Spring Launch",
        "Summer Refresh",
        "Back to School",
        "Holiday Gifting",
        "Always-On UGC",
    ]
    campaigns = pd.DataFrame(
        {
            "campaign_id": [f"camp_{i}" for i in range(len(campaign_names))],
            "campaign_name": campaign_names,
            "status": ["Completed", "Completed", "Completed", "Active", "Active"],
            "start_date": [now - pd.Timedelta(days=d) for d in [300, 220, 150, 45, 90]],
            "end_date": [now - pd.Timedelta(days=d) for d in [260, 190, 120, 5, 1]],
        }
    )

    post_rows = []
    link_rows = []
    email_rows = []
    post_seq = 0
    link_seq = 0
    email_seq = 0

    # A couple of deliberate "spike" days to make the anomaly detection page interesting.
    spike_days = {days_of_history - 10, days_of_history - 45, days_of_history - 80}

    archetype_rates = {
        # (base daily post probability, base daily link-click probability, email open probability)
        "superfan": (0.22, 0.30, 0.85),
        "steady": (0.07, 0.10, 0.55),
        "fading": (0.03, 0.04, 0.25),
        "ghost": (0.002, 0.003, 0.05),
        "new_never_started": (0.0, 0.0, 0.15),
    }

    for _, creator in creators.iterrows():
        creator_id = creator["creator_id"]
        archetype = creator["_archetype"]
        post_rate, link_rate, open_prob = archetype_rates[archetype]
        joined_days_ago = (now - creator["joined_date"]).days

        history_days = min(days_of_history, joined_days_ago) if archetype != "new_never_started" else min(
            21, joined_days_ago
        )

        for day_offset in range(history_days, 0, -1):
            day = now - pd.Timedelta(days=day_offset)
            day_index = days_of_history - day_offset
            spike_multiplier = 6.0 if day_index in spike_days else 1.0

            if rng.random() < min(post_rate * spike_multiplier, 0.9):
                campaign = campaigns.sample(random_state=rng.integers(0, 1_000_000)).iloc[0]
                post_rows.append(
                    {
                        "post_id": f"post_{post_seq}",
                        "creator_id": creator_id,
                        "campaign_id": campaign["campaign_id"],
                        "campaign_name": campaign["campaign_name"],
                        "platform": rng.choice(PLATFORMS),
                        "post_type": rng.choice(POST_TYPES),
                        "posted_at": day + pd.Timedelta(hours=int(rng.integers(0, 24))),
                        "views": int(rng.gamma(2.0, 4000)),
                        "likes": int(rng.gamma(2.0, 250)),
                        "comments": int(rng.gamma(1.5, 20)),
                        "shares": int(rng.gamma(1.2, 10)),
                        "engagement": float(rng.uniform(0.5, 8.0)),
                        "link_clicks": int(rng.gamma(1.5, 15)),
                    }
                )
                post_seq += 1

            if rng.random() < min(link_rate * spike_multiplier, 0.9):
                link_rows.append(
                    {
                        "event_id": f"linkclick_{link_seq}",
                        "creator_id": creator_id,
                        "link_id": f"link_{rng.integers(0, 25)}",
                        "link_label": rng.choice(
                            ["Shop My Look", "Referral Code", "Blog Post", "Affiliate Storefront"]
                        ),
                        "destination_url": "https://example.com/shop",
                        "clicked_at": day + pd.Timedelta(hours=int(rng.integers(0, 24))),
                        "campaign_id": campaigns.sample(random_state=rng.integers(0, 1_000_000)).iloc[0][
                            "campaign_id"
                        ],
                    }
                )
                link_seq += 1

        # Email sends: roughly weekly newsletter/nudge cadence.
        n_sends = max(1, history_days // 7)
        for send_i in range(n_sends):
            sent_at = now - pd.Timedelta(days=int(history_days - send_i * 7))
            opened = rng.random() < open_prob
            opened_at = sent_at + pd.Timedelta(hours=float(rng.uniform(1, 48))) if opened else pd.NaT
            email_rows.append(
                {
                    "event_id": f"email_{email_seq}",
                    "creator_id": creator_id,
                    "message_id": f"msg_{send_i}",
                    "subject": rng.choice(
                        [
                            "New brief just dropped!",
                            "You're missing out on this month's bonus",
                            "Quick reminder: content due Friday",
                            "See what other creators are posting",
                        ]
                    ),
                    "sent_at": sent_at,
                    "opened_at": opened_at,
                    "clicked_at": opened_at + pd.Timedelta(minutes=10) if opened and rng.random() < 0.4 else pd.NaT,
                }
            )
            email_seq += 1

    posts = pd.DataFrame(post_rows)
    links = pd.DataFrame(link_rows)
    email_events = pd.DataFrame(email_rows)
    creators = creators.drop(columns=["_archetype"])

    return DemoData(creators=creators, campaigns=campaigns, posts=posts, links=links, email_events=email_events)
