"""Email Engagement: track creator engagement with CRM emails, and cross
segments (clicked but never linked, linked but never posted, never opened)."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle  # noqa: E402

st.set_page_config(page_title="Email Engagement", page_icon="📧", layout="wide")

st.title("📧 Email Engagement")
st.caption("Who's opening (and clicking) CRM emails — and where that engagement isn't translating into activation.")

bundle = get_bundle()
summary = bundle["summary"]
segments = bundle["email_segments"]

emailed = summary[summary["emails_sent_total"] > 0] if "emails_sent_total" in summary.columns else summary
opened_ever = emailed["last_email_opened"].notna().sum() if not emailed.empty else 0
clicked_ever = emailed["last_email_clicked"].notna().sum() if not emailed.empty else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Creators emailed", f"{len(emailed):,}")
col2.metric("Ever opened", f"{opened_ever:,}", f"{opened_ever/len(emailed)*100:.0f}%" if len(emailed) else None)
col3.metric("Ever clicked", f"{clicked_ever:,}", f"{clicked_ever/len(emailed)*100:.0f}%" if len(emailed) else None)
col4.metric("Never opened", f"{len(segments['never_opened']):,}")

st.divider()

col_left, col_right = st.columns([2, 1])
with col_left:
    st.subheader("Days since last email open")
    dist = emailed.dropna(subset=["days_since_last_email_open"])
    if not dist.empty:
        fig = px.histogram(dist, x="days_since_last_email_open", nbins=25, color_discrete_sequence=["#9b59b6"])
        fig.update_layout(xaxis_title="Days since last open", yaxis_title="Creators")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No opens recorded yet.")

with col_right:
    st.subheader("Engagement funnel")
    funnel_df = pd.DataFrame(
        {
            "stage": ["Emailed", "Opened", "Clicked"],
            "count": [len(emailed), opened_ever, clicked_ever],
        }
    )
    fig2 = px.bar(funnel_df, x="stage", y="count", color="stage", text="count")
    fig2.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Creators")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.subheader("Engagement gaps worth investigating")

tab1, tab2, tab3 = st.tabs(
    [
        f"🖱️ Clicked but never created a link ({len(segments['clicked_no_link'])})",
        f"🔗 Created a link but never posted ({len(segments['linked_no_post'])})",
        f"📭 Never opened an email ({len(segments['never_opened'])})",
    ]
)

DISPLAY_COLUMNS = {
    "name": "Name",
    "handle": "Handle",
    "tier": "Tier",
    "last_email_sent": "Last Email Sent",
    "last_email_opened": "Last Email Opened",
    "last_email_clicked": "Last Email Clicked",
    "days_since_last_email_open": "Days Since Open",
    "days_since_last_email_click": "Days Since Click",
    "first_link": "First Link Date",
    "first_post": "First Post Date",
    "activation_state": "Activation State",
}


def render_segment(df, empty_message: str) -> None:
    if df.empty:
        st.success(empty_message)
        return
    cols = [c for c in DISPLAY_COLUMNS if c in df.columns]
    display = df[cols].rename(columns=DISPLAY_COLUMNS)
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Export to CSV",
        data=display.to_csv(index=False).encode("utf-8"),
        file_name="email_engagement_segment.csv",
        mime="text/csv",
        key=f"export_{empty_message[:10]}",
    )


with tab1:
    st.caption("They clicked through from an email but never created a trackable link — a warm lead worth a nudge.")
    render_segment(segments["clicked_no_link"], "Nobody's in this gap right now.")

with tab2:
    st.caption("They took the first activation step (a link) but haven't published content yet.")
    render_segment(segments["linked_no_post"], "Everyone who's linked has also posted.")

with tab3:
    st.caption("Email doesn't seem to be reaching them at all — consider a different outreach channel.")
    render_segment(segments["never_opened"], "Everyone has opened at least one email.")
