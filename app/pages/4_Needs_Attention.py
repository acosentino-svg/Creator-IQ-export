"""Needs Attention: a prioritized, exportable outreach list combining
activation segment + email coldness, plus an optional Slack digest."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import requests  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle, get_config, render_mode_badge  # noqa: E402

st.set_page_config(page_title="Needs Attention", page_icon="🚨", layout="wide")
config = get_config()
render_mode_badge()

st.title("🚨 Needs Attention")
st.caption(
    "Creators who are at risk, dormant, or never activated — cross-referenced with email "
    "coldness — ranked so outreach starts with the highest-value creators first."
)

bundle = get_bundle()
needs_attention = bundle["needs_attention"]

if needs_attention.empty:
    st.success("Nobody needs attention right now. 🎉")
    st.stop()

tiers = sorted(needs_attention["tier"].dropna().unique())
tier_filter = st.multiselect("Tier", tiers, default=list(tiers))
view = needs_attention[needs_attention["tier"].isin(tier_filter)] if tier_filter else needs_attention

col1, col2, col3 = st.columns(3)
col1.metric("Total needing attention", len(view))
col2.metric("Also email-cold", int(view["is_cold"].sum()))
vip_count = int((view["tier"] == "VIP").sum()) if "tier" in view.columns else 0
col3.metric("VIP creators in this list", vip_count)

st.dataframe(
    view[
        [
            "name",
            "tier",
            "activation_segment",
            "reason",
            "activation_score",
            "days_since_last_active",
            "days_since_last_open",
        ]
    ].sort_values(["tier", "activation_score"], ascending=[True, True]),
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "⬇️ Download outreach list (CSV)",
    data=view.to_csv(index=False).encode("utf-8"),
    file_name="creatoriq_needs_attention.csv",
    mime="text/csv",
)

st.divider()
st.subheader("Send weekly digest to Slack")
if not config.slack_webhook_url:
    st.info("Set `SLACK_WEBHOOK_URL` in `.env` to enable one-click Slack digests from this page.")
else:
    if st.button("Post digest to Slack now"):
        top = view.sort_values("activation_score").head(10)
        lines = [f"*Needs attention this week ({len(view)} creators):*"]
        for _, row in top.iterrows():
            lines.append(f"• {row['name']} ({row['tier']}) — {row['reason']}, score {row['activation_score']:.0f}")
        try:
            resp = requests.post(config.slack_webhook_url, json={"text": "\n".join(lines)}, timeout=10)
            resp.raise_for_status()
            st.success("Posted to Slack.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to post to Slack: {exc}")

with st.expander("How the priority order works"):
    st.markdown(
        """
        Sorted ascending by **activation score** within tier, so the lowest-scoring VIP/Core
        creators surface first — those are typically your highest-ROI re-engagement targets.
        Tune the underlying thresholds in `config/settings.yaml`:

        - `activation.active_window_days` / `at_risk_window_days` / `dormant_window_days`
        - `email_engagement.cold_after_days` / `cold_after_consecutive_unopened_sends`
        """
    )
