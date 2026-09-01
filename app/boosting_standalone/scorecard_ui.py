"""Shared Boosting Program Scorecard UI (standalone app + activation dashboard page)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from creatoriq_dashboard.boosting_data_access import (
    load_boosting_content,
    rebuild_boosting_from_cached_posts,
    save_boosting_content,
    sync_and_store_boosting_content,
)
from creatoriq_dashboard.boosting_demo_data import generate_demo_boosting_content
from creatoriq_dashboard.boosting_scorecard import (
    build_cohort_retention,
    build_creator_monthly,
    build_program_monthly,
    compute_creator_movement,
    format_program_value,
    latest_program_kpis,
    merge_content_raw,
    parse_content_raw_csv,
    program_monthly_pivot,
    program_trend_series,
)
from creatoriq_dashboard.config import AppConfig

SESSION_KEY = "boosting_content_raw"
LABEL_TO_METRIC = {
    "Eligible Boosting Creators": "eligible_boosting_creators",
    "Active Boosting Creators": "active_boosting_creators",
    "Activation Rate": "activation_rate",
    "Eligible Content Pieces": "eligible_content_pieces",
    "Selected Content Pieces": "selected_content_pieces",
    "Selection Rate": "selection_rate",
    "Creators Selected": "creators_selected",
    "% Active Creators Selected": "pct_active_creators_selected",
    "Avg Selections per Active Creator": "avg_selections_per_active_creator",
    "Gift Card Spend": "gift_card_spend",
    "Cost / Selected Asset": "cost_per_selected_asset",
    "Paid Media Spend": "paid_media_spend",
    "Boosted Revenue": "boosted_revenue",
    "ROAS": "roas",
    "Total Program ROI": "total_program_roi",
    "Retention Rate": "retention_rate",
    "New Creators": "new_creators",
    "Reactivated Creators": "reactivated_creators",
    "Lapsed Creators": "lapsed_creators",
    "Prior Month Active Creators": "prior_month_active_creators",
}


def _get_content(config: AppConfig) -> pd.DataFrame:
    if SESSION_KEY not in st.session_state:
        content, _ = load_boosting_content(config)
        st.session_state[SESSION_KEY] = content
    return st.session_state[SESSION_KEY]


def _set_content(df: pd.DataFrame) -> None:
    st.session_state[SESSION_KEY] = df


def render_boosting_scorecard(config: AppConfig) -> None:
    """Render the four-tab Boosting scorecard."""
    content = _get_content(config)
    _, sync_info = load_boosting_content(config)

    program_long = build_program_monthly(content)
    creator_monthly = build_creator_monthly(content)
    program_wide = program_monthly_pivot(program_long)
    trends = program_trend_series(program_long)

    st.title("🚀 Boosting Program Scorecard")
    st.caption(
        "Wayfair Boosting Partnership only. **Creators:** WBP tag or Wayfair Boosting Partnership campaign. "
        "**Eligible content:** both #WayfairCreator and #wayfairelevate in the caption."
    )

    if config.is_demo:
        st.warning(
            "**Demo mode** — Sync buttons are disabled until you connect CreatorIQ. "
            "You can still explore sample data below, or upload a CSV on the **Content Raw** tab."
        )
        with st.expander("How to enable sync (click here)", expanded=True):
            st.markdown(
                """
1. Open [share.streamlit.io](https://share.streamlit.io) → your Boosting app → **Manage app**
2. Go to **Settings** → **Secrets**
3. Paste:

```toml
CREATORIQ_API_KEY = "your-key-here"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
CREATORIQ_DASHBOARD_MODE = "live"
```

4. Click **Save** → **Reboot app**
5. Come back here — the sidebar should say **Live mode** and sync buttons will work.
                """
            )
    else:
        st.success(
            f"**Live mode** — posts synced: `{sync_info.get('posts') or 'never'}` · "
            f"boosting content: `{sync_info.get('boosting_content') or 'never'}`"
        )

    st.subheader("Data sources & sync")
    if config.is_demo:
        st.caption("Sync is off in demo mode. Use the steps above, or upload a CSV on **Content Raw**.")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Sync Boosting from CreatorIQ API", type="primary", disabled=config.is_demo):
            with st.spinner("Fetching boosting campaign activity from CreatorIQ..."):
                try:
                    _set_content(sync_and_store_boosting_content(config))
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"API sync failed: {exc}")
    with col_b:
        if st.button("Rebuild from cached posts", disabled=config.is_demo):
            with st.spinner("Rebuilding from warehouse posts..."):
                _set_content(rebuild_boosting_from_cached_posts(config))
                st.rerun()
    with col_c:
        if st.button("Reset to demo data"):
            _set_content(generate_demo_boosting_content())
            st.rerun()

    st.markdown(
        "**Program rules:** WBP tag or Wayfair Boosting Partnership campaign · "
        "Eligible content must include **#WayfairCreator** and **#wayfairelevate**."
    )

    tab_raw, tab_creator, tab_program, tab_dashboard = st.tabs(
        ["Content Raw", "Creator Monthly", "Program Monthly", "Dashboard"]
    )

    with tab_raw:
        st.subheader("Content Raw")
        st.markdown("One row per eligible Boosting content piece.")

        uploaded = st.file_uploader(
            "Upload monthly export (CSV) — merges with API data",
            type=["csv"],
            accept_multiple_files=True,
        )
        if uploaded:
            try:
                batches = [parse_content_raw_csv(f.getvalue()) for f in uploaded]
                merged_upload = batches[0]
                for batch in batches[1:]:
                    merged_upload = merge_content_raw(merged_upload, batch)
                st.success(f"Parsed **{len(merged_upload):,}** rows.")
                if st.button("Import uploaded data", type="primary"):
                    merged = merge_content_raw(content, merged_upload)
                    _set_content(merged)
                    if not config.is_demo:
                        save_boosting_content(config, merged)
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        filter_months = st.multiselect(
            "Filter by month",
            options=sorted(content["month"].unique()) if not content.empty else [],
            default=sorted(content["month"].unique()) if not content.empty else [],
        )
        view = content[content["month"].isin(filter_months)] if filter_months else content
        display = view.rename(
            columns={
                "creator_id": "Publisher ID",
                "month": "Month",
                "content_url": "Content URL",
                "platform": "Platform",
                "post_date": "Post Date",
                "eligible": "Eligible?",
                "selected": "Selected?",
                "selection_date": "Selection Date",
                "boosted": "Boosted?",
                "gift_card_cost": "Gift Card Cost",
                "paid_spend": "Paid Spend",
                "boosted_revenue": "Boosted Revenue",
                "impressions": "Impressions",
                "engagements": "Engagements",
                "clicks": "Clicks",
                "featured_category": "Featured Category",
                "campaign": "Campaign / Push",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True, height=420)
        st.download_button(
            "Download Content Raw (CSV)",
            data=content.to_csv(index=False).encode("utf-8"),
            file_name="boosting_content_raw.csv",
            mime="text/csv",
        )

    with tab_creator:
        st.subheader("Creator Monthly")
        st.markdown(
            "One row per **active** Boosting creator per month. Active ≠ selected — creators with zero "
            "selections still count as active participants."
        )

        month_options = sorted(creator_monthly["month"].unique()) if not creator_monthly.empty else []
        selected_month = st.selectbox("Month", month_options, index=max(len(month_options) - 1, 0))

        if selected_month:
            movement = compute_creator_movement(content, selected_month)
            cols = st.columns(5)
            for col, (_, row) in zip(cols, movement.iterrows()):
                col.metric(row["segment"], f"{int(row['creators']):,}")

        month_view = creator_monthly[creator_monthly["month"] == selected_month] if selected_month else creator_monthly
        if month_view.empty:
            st.info("No creator monthly data yet.")
        else:
            show = month_view.rename(
                columns={
                    "creator_id": "Publisher ID",
                    "eligible_pieces": "Eligible Pieces",
                    "selected_pieces": "Selected",
                    "selection_rate_pct": "Selection Rate %",
                    "gift_card_cost": "Gift Card Cost",
                    "paid_spend": "Spend",
                    "boosted_revenue": "Revenue",
                    "roas_display": "ROAS",
                    "active_last_month": "Active Last Month?",
                    "retention_status": "Status",
                }
            )
            st.dataframe(show, use_container_width=True, hide_index=True)

        st.subheader("Cohort retention")
        cohorts = build_cohort_retention(content)
        if cohorts.empty:
            st.info("Not enough history for cohort retention yet.")
        else:
            cohort_display = cohorts.copy()
            for col in [c for c in cohort_display.columns if c.startswith("month_")]:
                cohort_display[col] = cohort_display[col].map(
                    lambda v: f"{v * 100:.0f}%" if pd.notna(v) and v is not None else ""
                )
            st.dataframe(cohort_display, use_container_width=True, hide_index=True)

    with tab_program:
        st.subheader("Program Monthly")
        if program_wide.empty:
            st.info("No program metrics yet.")
        else:
            display_wide = program_wide.copy()
            for col in display_wide.columns[1:]:
                display_wide[col] = [
                    format_program_value(LABEL_TO_METRIC.get(metric_name, ""), val)
                    for metric_name, val in zip(display_wide["Metric"], display_wide[col])
                ]
            st.dataframe(display_wide, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Program Monthly (CSV)",
                data=program_wide.to_csv(index=False).encode("utf-8"),
                file_name="boosting_program_monthly.csv",
                mime="text/csv",
            )

    with tab_dashboard:
        st.subheader("Dashboard")
        kpis = latest_program_kpis(program_long)
        if not kpis:
            st.info("Upload or sync content to see KPIs.")
        else:
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Active Creators", f"{int(kpis.get('active_boosting_creators') or 0):,}")
            c2.metric("Eligible Content", f"{int(kpis.get('eligible_content_pieces') or 0):,}")
            c3.metric("Selection Rate", format_program_value("selection_rate", kpis.get("selection_rate")))
            c4.metric("Retention", format_program_value("retention_rate", kpis.get("retention_rate")))
            c5.metric("Boosted Revenue", format_program_value("boosted_revenue", kpis.get("boosted_revenue")))
            c6.metric("ROAS", format_program_value("roas", kpis.get("roas")))

            chart_left, chart_mid, chart_right = st.columns(3)
            with chart_left:
                st.markdown("**Active creators** (retained / new / reactivated)")
                if not trends.empty:
                    retained = (
                        trends.get("active_boosting_creators", pd.Series(dtype=float)).fillna(0)
                        - trends.get("new_creators", pd.Series(dtype=float)).fillna(0)
                        - trends.get("reactivated_creators", pd.Series(dtype=float)).fillna(0)
                    )
                    fig = go.Figure()
                    fig.add_trace(go.Bar(name="Retained", x=trends["month_label"], y=retained))
                    fig.add_trace(go.Bar(name="New", x=trends["month_label"], y=trends.get("new_creators", 0)))
                    fig.add_trace(
                        go.Bar(name="Reactivated", x=trends["month_label"], y=trends.get("reactivated_creators", 0))
                    )
                    fig.update_layout(barmode="stack", height=360, margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig, use_container_width=True)

            with chart_mid:
                st.markdown("**Eligible vs. selected content**")
                if not trends.empty:
                    fig2 = px.bar(
                        trends,
                        x="month_label",
                        y=["eligible_content_pieces", "selected_content_pieces"],
                        barmode="group",
                    )
                    fig2.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10), legend_title=None)
                    st.plotly_chart(fig2, use_container_width=True)

            with chart_right:
                st.markdown("**Retention rate over time**")
                if not trends.empty and "retention_rate" in trends.columns:
                    ret = trends.copy()
                    ret["retention_pct"] = ret["retention_rate"] * 100
                    fig3 = px.line(ret, x="month_label", y="retention_pct", markers=True)
                    fig3.update_layout(yaxis_title="Retention %", xaxis_title=None, height=360)
                    st.plotly_chart(fig3, use_container_width=True)

            st.caption(
                "ROAS = boosted revenue ÷ paid media spend (gift cards excluded). "
                "Upload CSV for paid metrics if CreatorIQ doesn't expose them via API."
            )
