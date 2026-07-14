"""Synthetic CreatorIQ-shaped data so the dashboard is fully explorable
without live API credentials. Useful for local development, demos, and
tests. Set CREATORIQ_DASHBOARD_MODE=demo (the default) to use this.

Deliberately builds creators with distinct behavioral archetypes so every
activation state the dashboard computes (never activated, active, went
dark, newly activated, reactivated, consistently active) has real examples
to show off, instead of a uniformly random population.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TIERS = ["VIP", "Core", "Emerging", "New"]
PLATFORMS = ["Instagram", "TikTok", "YouTube", "Pinterest"]
POST_TYPES = ["Reel", "Static Post", "Story", "Video"]
STATUSES = ["Accepted", "Applied", "Pending"]

TAG_POOL = [
    "Home & Garden",
    "Beauty",
    "Fashion",
    "Fitness",
    "Food",
    "Parenting",
    "Tech",
    "Travel",
    "VIP",
    "Ambassador",
    "Affiliate",
    "New Recruit",
]

EMAIL_SUBJECTS = [
    "New brief just dropped!",
    "You're missing out on this month's bonus",
    "Quick reminder: content due Friday",
    "See what other creators are posting",
    "Your custom link is ready",
    "Program update: new payout tiers",
]

# (archetype, weight, post_rate, link_rate, open_prob, click_given_open_prob, description)
# Rates are *daily* probabilities during an "active" stretch.
ARCHETYPES = {
    # Been active the whole time, no real gaps -> "Consistently Active"
    "consistently_active": dict(weight=0.14, post_rate=0.09, link_rate=0.05, open_prob=0.75, click_prob=0.5),
    # Active recently but had a long dark stretch earlier -> "Reactivated"
    "reactivated": dict(weight=0.10, post_rate=0.10, link_rate=0.06, open_prob=0.6, click_prob=0.35),
    # Was active, stopped a while ago and hasn't come back -> "Went Dark"
    "went_dark": dict(weight=0.16, post_rate=0.08, link_rate=0.04, open_prob=0.2, click_prob=0.1),
    # Cooling off: active-ish in the past, quiet lately but not dark yet -> "Inactive"
    "cooling_off": dict(weight=0.14, post_rate=0.04, link_rate=0.02, open_prob=0.35, click_prob=0.15),
    # Just joined and had their first-ever post/link very recently -> "Newly Activated"
    "newly_activated": dict(weight=0.12, post_rate=0.18, link_rate=0.12, open_prob=0.7, click_prob=0.45),
    # Joined, created a trackable link, but never actually posted
    "linked_no_post": dict(weight=0.06, post_rate=0.0, link_rate=0.05, open_prob=0.5, click_prob=0.3),
    # Onboarded but has done absolutely nothing -> "Never Activated"
    "never_activated": dict(weight=0.15, post_rate=0.0, link_rate=0.0, open_prob=0.15, click_prob=0.05),
    # Reliable middle-of-the-road creators, active in the recent window
    "steady": dict(weight=0.13, post_rate=0.07, link_rate=0.04, open_prob=0.55, click_prob=0.3),
}


@dataclass
class DemoData:
    creators: pd.DataFrame
    campaigns: pd.DataFrame
    posts: pd.DataFrame
    links: pd.DataFrame
    email_events: pd.DataFrame


def _slugify(name: str, idx: int) -> str:
    base = "".join(ch for ch in name.lower() if ch.isalnum())
    return f"@{base}{idx % 97}"


def generate_demo_data(n_creators: int = 220, days_of_history: int = 150, seed: int = 42) -> DemoData:
    rng = np.random.default_rng(seed)
    now = pd.Timestamp.now(tz="UTC").normalize()

    archetype_names = list(ARCHETYPES.keys())
    archetype_weights = np.array([ARCHETYPES[a]["weight"] for a in archetype_names])
    archetype_weights = archetype_weights / archetype_weights.sum()

    joined_offsets = rng.integers(20, 500, size=n_creators)
    tiers = rng.choice(TIERS, size=n_creators, p=[0.08, 0.27, 0.35, 0.30])
    statuses = rng.choice(STATUSES, size=n_creators, p=[0.82, 0.12, 0.06])
    archetypes = rng.choice(archetype_names, size=n_creators, p=archetype_weights)

    first_names = [
        "Ava", "Liam", "Sophia", "Noah", "Isabella", "Mason", "Mia", "Ethan", "Amelia", "Lucas",
        "Harper", "Elijah", "Evelyn", "James", "Abigail", "Benjamin", "Emily", "Logan", "Ella", "Alex",
    ]
    last_names = [
        "Reed", "Cohen", "Patterson", "Nguyen", "Garcia", "Bennett", "Foster", "Hayes", "Coleman", "Brooks",
        "Sanders", "Rivera", "Bell", "Ward", "Price", "Long", "Ross", "Wood", "Barnes", "Kelly",
    ]

    creator_rows = []
    for i in range(n_creators):
        first = first_names[i % len(first_names)]
        last = last_names[(i * 7) % len(last_names)]
        name = f"{first} {last}"
        n_tags = rng.integers(1, 4)
        tags = sorted(set(rng.choice(TAG_POOL, size=n_tags, replace=False).tolist()))
        creator_rows.append(
            {
                "creator_id": f"cr_{i:04d}",
                "name": name,
                "handle": _slugify(name, i),
                "email": f"{first.lower()}.{last.lower()}{i}@example.com",
                "status": statuses[i],
                "tier": tiers[i],
                "tags": ", ".join(tags),
                "joined_date": now - pd.Timedelta(days=int(joined_offsets[i])),
                "_archetype": archetypes[i],
            }
        )
    creators = pd.DataFrame(creator_rows)

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

    post_rows: list[dict] = []
    link_rows: list[dict] = []
    email_rows: list[dict] = []
    post_seq = link_seq = email_seq = 0

    # A few deliberate "spike" days so the Momentum page has something to find.
    spike_day_indices = {days_of_history - 3, days_of_history - 20, days_of_history - 55}

    for _, creator in creators.iterrows():
        creator_id = creator["creator_id"]
        archetype = creator["_archetype"]
        cfg = ARCHETYPES[archetype]
        joined_days_ago = (now - creator["joined_date"]).days
        history_days = min(days_of_history, int(joined_days_ago))

        if archetype == "never_activated":
            # Onboarded, but truly nothing -- skip straight to email-only history.
            active_ranges: list[tuple[int, int]] = []
        elif archetype == "newly_activated":
            # First-ever activity happened in just the last ~10 days.
            start = max(1, min(10, history_days))
            active_ranges = [(start, 0)]
        elif archetype == "went_dark":
            # Active for a good early stretch, then nothing for a long time.
            dark_for = rng.integers(70, 120)
            active_end = min(history_days, int(dark_for))
            active_ranges = [(history_days, active_end)] if history_days > active_end else []
        elif archetype == "cooling_off":
            # Active until a more moderate ~35-55 days ago.
            quiet_for = rng.integers(35, 55)
            active_end = min(history_days, int(quiet_for))
            active_ranges = [(history_days, active_end)] if history_days > active_end else []
        elif archetype == "reactivated":
            # Active early, a long dark gap, then active again recently.
            gap_start = min(history_days, int(rng.integers(90, 130)))
            gap_end = min(gap_start, int(rng.integers(5, 20)))
            active_ranges = [(history_days, gap_start), (gap_end, 0)]
        elif archetype == "linked_no_post":
            active_ranges = [(history_days, 0)]
        else:  # consistently_active, steady
            active_ranges = [(history_days, 0)]

        for day_offset in range(history_days, 0, -1):
            in_active_range = any(end <= day_offset <= start for start, end in active_ranges)
            if not in_active_range:
                continue
            day = now - pd.Timedelta(days=day_offset)
            day_index = days_of_history - day_offset
            spike_multiplier = 6.0 if day_index in spike_day_indices else 1.0

            if archetype != "linked_no_post" and rng.random() < min(cfg["post_rate"] * spike_multiplier, 0.9):
                campaign = campaigns.sample(random_state=int(rng.integers(0, 1_000_000))).iloc[0]
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
                    }
                )
                post_seq += 1

            if rng.random() < min(cfg["link_rate"] * spike_multiplier, 0.9):
                link_rows.append(
                    {
                        "link_id": f"link_{link_seq}",
                        "creator_id": creator_id,
                        "label": rng.choice(["Shop My Look", "Referral Code", "Blog Post", "Affiliate Storefront"]),
                        "destination_url": "https://example.com/shop",
                        "created_at": day + pd.Timedelta(hours=int(rng.integers(0, 24))),
                        "campaign_id": campaigns.sample(random_state=int(rng.integers(0, 1_000_000))).iloc[0][
                            "campaign_id"
                        ],
                    }
                )
                link_seq += 1

        # Email sends: roughly weekly cadence for as long as they've been in the program.
        n_sends = max(1, min(history_days, days_of_history) // 7)
        for send_i in range(n_sends):
            sent_at = now - pd.Timedelta(days=int(min(history_days, days_of_history) - send_i * 7))
            opened = rng.random() < cfg["open_prob"]
            opened_at = sent_at + pd.Timedelta(hours=float(rng.uniform(1, 48))) if opened else pd.NaT
            clicked = opened and rng.random() < cfg["click_prob"]
            clicked_at = opened_at + pd.Timedelta(minutes=15) if clicked else pd.NaT
            email_rows.append(
                {
                    "event_id": f"email_{email_seq}",
                    "creator_id": creator_id,
                    "message_id": f"msg_{send_i}",
                    "subject": rng.choice(EMAIL_SUBJECTS),
                    "sent_at": sent_at,
                    "opened_at": opened_at,
                    "clicked_at": clicked_at,
                }
            )
            email_seq += 1

    posts = pd.DataFrame(post_rows)
    links = pd.DataFrame(link_rows)
    email_events = pd.DataFrame(email_rows)
    creators = creators.drop(columns=["_archetype"])

    return DemoData(creators=creators, campaigns=campaigns, posts=posts, links=links, email_events=email_events)
