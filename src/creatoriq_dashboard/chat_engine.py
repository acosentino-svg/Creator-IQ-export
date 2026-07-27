"""Natural-language chat assistant for activation data.

Parses plain-English questions into structured queries, runs them against
the dashboard data bundle, and returns a text summary plus an optional table.

Works out of the box with a rule-based parser. Set OPENAI_API_KEY in .env to
enable LLM parsing for more flexible phrasing.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests

from creatoriq_dashboard.activation_analytics import (
    STRUGGLE_SEGMENT_META,
    ActivationContext,
    build_outreach_queue,
    compute_activation_funnel,
    compute_activation_trends,
    compute_cohort_activation,
    compute_extended_kpis,
    compute_struggle_segments,
    enrich_activation_fields,
    filter_first_activations,
    filter_first_links,
    filter_first_posts,
)
from creatoriq_dashboard.metrics import resolve_date_range

DISPLAY_COLUMNS = [
    "name",
    "handle",
    "email",
    "tier",
    "tags",
    "joined_date",
    "first_post",
    "first_link",
    "first_activity_at",
    "last_activity_at",
    "days_since_join",
    "days_since_last_activity",
    "activation_state",
    "struggle_segment",
]

SEGMENT_ALIASES: dict[str, str] = {
    "ghost": "ghost",
    "ghosts": "ghost",
    "never activated": "never_activated",
    "never activate": "never_activated",
    "inactive": "ghost",
    "linked but never posted": "linked_no_post",
    "linked no post": "linked_no_post",
    "link but no post": "linked_no_post",
    "has link no post": "linked_no_post",
    "posted but never linked": "posted_no_link",
    "posted no link": "posted_no_link",
    "post but no link": "posted_no_link",
    "missing commission": "posted_no_link",
    "no commission": "posted_no_link",
    "went dark": "went_dark",
    "dark": "went_dark",
    "cooling": "cooling",
    "cooling off": "cooling",
    "one and done": "one_and_done",
    "one-and-done": "one_and_done",
    "clicked email": "email_clicked_stuck",
    "opened email": "email_opened_stuck",
    "active": "active",
    "healthy": "healthy",
    "new joiner": "new_monitor",
    "new joiners": "new_monitor",
}

PERIOD_ALIASES: dict[str, str] = {
    "this week": "Last 7 days",
    "past week": "Last 7 days",
    "last week": "Last 7 days",
    "this month": "This Month",
    "past month": "Last 30 days",
    "last 30 days": "Last 30 days",
    "last 7 days": "Last 7 days",
    "last 60 days": "Last 60 days",
    "last 90 days": "Last 90 days",
    "today": "Last 7 days",
}


@dataclass
class QuerySpec:
    intent: str
    limit: int = 25
    period: str = "Last 7 days"
    segment: str | None = None
    tier: str | None = None
    search_term: str | None = None
    metric: str | None = None
    sort_by: str | None = None
  # ascending for days_since (oldest first) vs descending for counts
    ascending: bool = False


@dataclass
class ChatResponse:
    message: str
    table: pd.DataFrame | None = None
    spec: QuerySpec | None = None
    suggestions: list[str] = field(default_factory=list)


def _extract_limit(text: str, default: int = 25) -> int:
    m = re.search(r"\b(\d{1,4})\s*(?:creators?|people|rows?|results?)\b", text, re.I)
    if m:
        return min(int(m.group(1)), 500)
    m = re.search(r"\btop\s+(\d{1,4})\b", text, re.I)
    if m:
        return min(int(m.group(1)), 500)
    m = re.search(r"\bgive me\s+(\d{1,4})\b", text, re.I)
    if m:
        return min(int(m.group(1)), 500)
    if re.search(r"\ba few\b", text, re.I):
        return 10
    if re.search(r"\bsome\b", text, re.I):
        return 15
    return default


def _extract_period(text: str) -> str:
    lower = text.lower()
    for phrase, preset in sorted(PERIOD_ALIASES.items(), key=lambda x: -len(x[0])):
        if phrase in lower:
            return preset
    return "Last 7 days"


def _extract_segment(text: str) -> str | None:
    lower = text.lower()
    for phrase, seg_id in sorted(SEGMENT_ALIASES.items(), key=lambda x: -len(x[0])):
        if phrase in lower:
            return seg_id
    return None


def _extract_tier(text: str) -> str | None:
    for tier in ("VIP", "Core", "Emerging", "New"):
        if re.search(rf"\b{tier}\b", text, re.I):
            return tier
    return None


def parse_user_message(message: str) -> QuerySpec:
    """Rule-based NL parser. Returns a QuerySpec for execute_query."""
    text = message.strip()
    lower = text.lower()
    limit = _extract_limit(text)
    period = _extract_period(text)
    segment = _extract_segment(text)
    tier = _extract_tier(text)

    llm_spec = _try_llm_parse(text)
    if llm_spec is not None:
        return llm_spec

    # --- Count / how many ---
    if re.search(r"\b(how many|count|number of|total)\b", lower):
        if segment:
            return QuerySpec(intent="count_segment", segment=segment, period=period)
        if re.search(r"\bactivat", lower):
            return QuerySpec(intent="activation_stats", period=period)
        return QuerySpec(intent="activation_stats", period=period)

    # --- Rates / stats / funnel ---
    if re.search(r"\b(rate|funnel|stats|statistics|overview|breakdown|percent)\b", lower):
        return QuerySpec(intent="activation_stats", period=period)

    # --- Cohort ---
    if re.search(r"\bcohort", lower):
        return QuerySpec(intent="cohort_table", limit=limit)

    # --- First activation / first time ---
    if re.search(r"\bfirst[- ]?(time|ever)\b", lower) and re.search(r"\b(activat|post|link)\b", lower):
        if re.search(r"\bpost", lower) and not re.search(r"\blink\b", lower):
            return QuerySpec(intent="first_posts", limit=limit, period=period)
        if re.search(r"\blink\b", lower) and not re.search(r"\bpost", lower):
            return QuerySpec(intent="first_links", limit=limit, period=period)
        return QuerySpec(intent="first_activations", limit=limit, period=period)

    if re.search(r"\b(newly activat|new activat|just activat)\b", lower):
        return QuerySpec(intent="first_activations", limit=limit, period=period)

    # --- Segment list ---
    if segment:
        return QuerySpec(intent="segment_list", segment=segment, limit=limit, period=period, tier=tier)

    # --- Went dark / outreach ---
    if re.search(r"\b(outreach|priority|queue|who (should|needs)|nudge)\b", lower):
        return QuerySpec(intent="outreach_queue", limit=limit)

    # --- Search by name ---
    m = re.search(r'\b(?:named?|called|handle|@)\s+["\']?([\w.@_-]+)', text, re.I)
    if m:
        return QuerySpec(intent="search", search_term=m.group(1), limit=limit)

    # --- Longest idle / days since ---
    if re.search(r"\b(longest|most days|oldest|idle|quiet)\b", lower):
        return QuerySpec(intent="longest_idle", limit=limit, tier=tier)

    # --- Recently active ---
    if re.search(r"\b(recently active|active creators|currently active)\b", lower):
        return QuerySpec(intent="active_list", limit=limit, tier=tier)

    # --- List all / show creators ---
    if re.search(r"\b(list|show|give me|get|find|pull)\b", lower):
        if re.search(r"\bactivat", lower):
            return QuerySpec(intent="first_activations", limit=limit, period=period, tier=tier)
        return QuerySpec(intent="segment_list", segment=segment or "ghost", limit=limit, tier=tier)

    # --- Help ---
    if re.search(r"\b(help|what can you|examples?|commands?)\b", lower):
        return QuerySpec(intent="help")

    return QuerySpec(intent="help")


def _try_llm_parse(message: str) -> QuerySpec | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    system = """You parse questions about a creator activation program into JSON.
Return ONLY valid JSON with keys: intent, limit, period, segment, tier, search_term.
intents: first_activations, first_posts, first_links, segment_list, count_segment,
activation_stats, cohort_table, outreach_queue, active_list, longest_idle, search, help.
period values: Last 7 days, Last 30 days, Last 60 days, Last 90 days, This Month.
segment values: ghost, linked_no_post, posted_no_link, went_dark, never_activated, active, healthy, cooling, one_and_done, email_clicked_stuck, email_opened_stuck, new_monitor.
Default limit: 25. Default period: Last 7 days."""

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = json.loads(resp.json()["choices"][0]["message"]["content"])
        return QuerySpec(
            intent=data.get("intent", "help"),
            limit=min(int(data.get("limit", 25)), 500),
            period=data.get("period", "Last 7 days"),
            segment=data.get("segment"),
            tier=data.get("tier"),
            search_term=data.get("search_term"),
        )
    except Exception:
        return None


def _format_table(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    cols = [c for c in DISPLAY_COLUMNS if c in df.columns]
    extra = [c for c in df.columns if c not in cols and c not in ("creator_id",)]
    out = df[cols + extra[:3]].head(limit)
    return out


def execute_query(spec: QuerySpec, ctx: ActivationContext) -> ChatResponse:
    enriched = enrich_activation_fields(ctx.summary)
    classified = ctx.classified
    range_start, range_end = resolve_date_range(spec.period)

    suggestions = [
        "Give me 10 creators that activated for the first time this week",
        "How many creators are ghosts (joined but never did anything)?",
        "Show me creators who posted but never linked",
        "What's our activation funnel breakdown?",
        "List 25 creators in the outreach priority queue",
        "Who are the VIP creators that went dark?",
    ]

    if spec.intent == "help":
        return ChatResponse(
            message=(
                "I can answer questions about creator activation. Try asking:\n\n"
                "• **\"Give me 10 creators that activated for the first time this week\"**\n"
                "• **\"How many creators linked but never posted?\"**\n"
                "• **\"Show posted but never linked creators\"** (commission miss list)\n"
                "• **\"What's our activation rate?\"** or **\"Show the funnel\"**\n"
                "• **\"Who went dark?\"** or **\"Outreach priority queue\"**\n"
                "• **\"Cohort activation by join month\"**\n"
                "• **\"25 recently active VIP creators\"**\n\n"
                "I'll return a summary and a table you can download."
            ),
            suggestions=suggestions,
            spec=spec,
        )

    if spec.intent == "activation_stats":
        kpis = compute_extended_kpis(enriched, classified)
        funnel = compute_activation_funnel(enriched)
        msg = (
            f"**Program activation snapshot** ({len(enriched):,} creators enrolled)\n\n"
            f"- **Ever activated** (linked or posted at least once): "
            f"{kpis.get('ever_activated_count', 0):,} ({kpis.get('ever_activated_rate', 0)}%)\n"
            f"- **Fully activated** (both link AND post): "
            f"{kpis.get('fully_activated_count', 0):,} ({kpis.get('fully_activated_rate', 0)}%)\n"
            f"- **Activated within 14 days of joining**: "
            f"{kpis.get('activated_within_14d_rate', 0)}% of eligible creators\n"
            f"- **Activated within 30 days**: {kpis.get('activated_within_30d_rate', 0)}%\n"
            f"- **Ghosts** (joined 14+ days, zero activity): "
            f"{kpis.get('ghost_count', 0):,} ({kpis.get('ghost_rate', 0)}%)\n"
            f"- **Linked only** (no post): {kpis.get('linked_only_count', 0):,}\n"
            f"- **Posted only** (no link): {kpis.get('posted_only_count', 0):,}\n"
            f"- **Median days to first activity**: {kpis.get('median_days_to_first_activity', 'n/a')}\n"
            f"- **Currently active**: {kpis.get('active_creators', 0):,} · "
            f"**Went dark**: {kpis.get('went_dark_creators', 0):,}"
        )
        return ChatResponse(message=msg, table=funnel, spec=spec, suggestions=suggestions)

    if spec.intent == "cohort_table":
        cohorts = compute_cohort_activation(enriched)
        msg = f"**Cohort activation** by join month ({len(cohorts)} cohorts). See table for 14-day and 30-day rates."
        return ChatResponse(message=msg, table=cohorts.head(spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "count_segment":
        seg = spec.segment or "ghost"
        df = _segment_dataframe(enriched, classified, seg, spec.tier)
        label = STRUGGLE_SEGMENT_META.get(seg, {}).get("label", seg.replace("_", " ").title())
        msg = f"**{len(df):,} creators** match **{label}**."
        if spec.tier:
            msg += f" (filtered to tier: {spec.tier})"
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "first_activations":
        df = filter_first_activations(enriched, range_start, range_end)
        if spec.tier and "tier" in df.columns:
            df = df[df["tier"].str.lower() == spec.tier.lower()]
        msg = (
            f"**{len(df):,} creators** had their **first-ever activation** "
            f"(first link or post) between **{range_start.date()}** and **{range_end.date()}**."
        )
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "first_posts":
        df = filter_first_posts(enriched, range_start, range_end)
        if spec.tier and "tier" in df.columns:
            df = df[df["tier"].str.lower() == spec.tier.lower()]
        msg = f"**{len(df):,} creators** published their **first-ever post** in **{spec.period}**."
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "first_links":
        df = filter_first_links(enriched, range_start, range_end)
        if spec.tier and "tier" in df.columns:
            df = df[df["tier"].str.lower() == spec.tier.lower()]
        msg = f"**{len(df):,} creators** created their **first-ever link** in **{spec.period}**."
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "segment_list":
        seg = spec.segment or "ghost"
        df = _segment_dataframe(enriched, classified, seg, spec.tier)
        label = STRUGGLE_SEGMENT_META.get(seg, {}).get("label", seg.replace("_", " ").title())
        showing = min(len(df), spec.limit)
        msg = f"Here are **{showing}** of **{len(df):,}** creators in **{label}**."
        if spec.tier:
            msg += f" (tier: {spec.tier})"
        intervention = STRUGGLE_SEGMENT_META.get(seg, {}).get("intervention")
        if intervention:
            msg += f"\n\n**Suggested action:** {intervention}"
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "outreach_queue":
        queue = build_outreach_queue(enriched, classified)
        if spec.tier and "tier" in queue.columns:
            queue = queue[queue["tier"].str.lower() == spec.tier.lower()]
        msg = (
            f"**Outreach priority queue** — {len(queue):,} creators need attention "
            f"(sorted by segment priority). Showing top {min(len(queue), spec.limit)}."
        )
        return ChatResponse(message=msg, table=queue.head(spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "active_list":
        df = classified[classified["activation_state"] == "Active"].copy()
        if spec.tier and "tier" in df.columns:
            df = df[df["tier"].str.lower() == spec.tier.lower()]
        msg = f"**{len(df):,} currently active creators** (posted or linked within the active window)."
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "longest_idle":
        df = enriched[enriched["has_ever_activated"]].copy()
        if df.empty:
            df = enriched[~enriched["has_ever_activated"]].copy()
        df = df.sort_values("days_since_last_activity", ascending=False, na_position="last")
        if spec.tier and "tier" in df.columns:
            df = df[df["tier"].str.lower() == spec.tier.lower()]
        msg = f"Creators with the **longest time since last activity** (showing {spec.limit})."
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    if spec.intent == "search":
        term = (spec.search_term or "").lower().lstrip("@")
        mask = pd.Series(False, index=enriched.index)
        for col in ("name", "handle", "email", "creator_id"):
            if col in enriched.columns:
                mask |= enriched[col].astype(str).str.lower().str.contains(term, na=False)
        df = enriched[mask]
        msg = f"**{len(df):,} creators** match **{spec.search_term}**."
        return ChatResponse(message=msg, table=_format_table(df, spec.limit), spec=spec, suggestions=suggestions)

    return ChatResponse(
        message="I didn't quite understand that. Try one of the example questions below.",
        suggestions=suggestions,
        spec=spec,
    )


def _segment_dataframe(
    enriched: pd.DataFrame,
    classified: pd.DataFrame,
    segment_id: str,
    tier: str | None,
) -> pd.DataFrame:
    from creatoriq_dashboard.activation_analytics import assign_struggle_segment

    merged = enriched.merge(classified, on="creator_id", how="left", suffixes=("", "_dup"))
    if "activation_state_dup" in merged.columns:
        merged = merged.drop(columns=["activation_state_dup"])
    merged["struggle_segment"] = merged.apply(assign_struggle_segment, axis=1)

    if segment_id == "never_activated":
        df = merged[~merged["has_ever_activated"]]
    elif segment_id == "active":
        df = merged[merged["activation_state"] == "Active"]
    else:
        df = merged[merged["struggle_segment"] == segment_id]

    if tier and "tier" in df.columns:
        df = df[df["tier"].astype(str).str.lower() == tier.lower()]
    return df.sort_values("days_since_join", ascending=False)


def chat_turn(message: str, ctx: ActivationContext) -> ChatResponse:
    spec = parse_user_message(message)
    return execute_query(spec, ctx)
