"""Overview + top creators chart (active creator report)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from creatoriq_dashboard.active_creator_report_kpis import compute_active_creator_overview
from creatoriq_dashboard.boosting_selection_upload import load_boosting_selections


def _fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def render_report_overview(
    summary: pd.DataFrame,
    posts: pd.DataFrame,
    links: pd.DataFrame,
    transactions: pd.DataFrame,
    diagnostics,
    *,
    config,
) -> dict:
    ov = compute_active_creator_overview(summary, posts, links, transactions, diagnostics)

    st.markdown("### Overview")
    st.caption("**Active Creators** = linked and/or posted in range. Transactions alone do not count.")
    if ov.get("hybrid_line"):
        st.markdown(ov["hybrid_line"])

    selections = load_boosting_selections(config)
    if not selections.empty:
        sel = selections[selections.get("selected", False) == True]  # noqa: E712
        months = sorted(selections.get("selection_month", pd.Series(dtype=str)).astype(str).unique())
        month_hint = f" (months: {', '.join(m for m in months if m and m != 'nan')[:80]})" if months else ""
        st.caption(f"**Monthly selections on file:** {len(sel):,} creators marked selected{month_hint}")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Active Creators", f"{ov['active_creators']:,}")
        st.metric("Posting Creators", f"{ov['posting_creators']:,}")
        st.metric("Total Posts", f"{ov['total_posts']:,}")
    with c2:
        st.metric("Link Generating Creators", f"{ov['linking_creators']:,}")
        st.metric("Links Generated", f"{ov['total_links']:,}")
    with c3:
        st.metric("RPIs", f"{ov['rpis']:,}")
        st.metric("Total Sale Amount", _fmt_money(float(ov["total_sales"])))

    top = ov.get("top_25", pd.DataFrame())
    if top is not None and not top.empty:
        st.markdown("### Top creators")
        chart_df = top.head(25).copy()
        label_col = "name" if "name" in chart_df.columns else "creator_id"
        chart_df["label"] = chart_df[label_col].fillna(chart_df["creator_id"]).astype(str).str.slice(0, 32)
        posts_col = chart_df.get("posts_in_range", pd.Series(0, index=chart_df.index)).fillna(0)
        links_col = chart_df.get("links_in_range", pd.Series(0, index=chart_df.index)).fillna(0)
        tx_col = chart_df.get("transactions_in_range", chart_df.get("order_count", 0)).fillna(0)

        fig = go.Figure()
        fig.add_bar(name="Posts", x=chart_df["label"], y=posts_col, marker_color="#3b82f6")
        fig.add_bar(name="Links", x=chart_df["label"], y=links_col, marker_color="#10b981")
        fig.add_bar(name="Transactions", x=chart_df["label"], y=tx_col, marker_color="#f59e0b")
        fig.update_layout(
            barmode="group",
            height=420,
            margin=dict(l=20, r=20, t=40, b=120),
            xaxis_tickangle=-45,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            title="Top 25 creators — posts, links, transactions (activity window)",
        )
        st.plotly_chart(fig, use_container_width=True)

    return ov
