"""Gift-card / lapsed-creator activation outreach lists (Sep, Oct, etc.)."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def _norm_id(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _norm_name(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def parse_activation_outreach_csv(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    """Parse CreatorIQ-style outreach export (CreatorId and/or Publisher ID + Creator name)."""
    raw = pd.read_csv(source) if not isinstance(source, pd.DataFrame) else source.copy()
    if raw.empty:
        return pd.DataFrame(columns=["creator_id", "publisher_id", "creator_name", "tags"])

    id_col = next((c for c in raw.columns if c.strip().lower() in {"creatorid", "creator id"}), None)
    pub_col = next(
        (c for c in raw.columns if "publisher" in c.lower() and "id" in c.lower()),
        None,
    )
    name_col = next((c for c in raw.columns if c.strip().lower() == "creator"), None)
    if not name_col:
        name_col = next((c for c in raw.columns if "creator name" in c.lower()), None)
    tags_col = next((c for c in raw.columns if c.strip().lower() == "tags"), None)

    rows: list[dict] = []
    for _, row in raw.iterrows():
        rows.append(
            {
                "creator_id": _norm_id(row.get(id_col)) if id_col else "",
                "publisher_id": _norm_id(row.get(pub_col)) if pub_col else "",
                "creator_name": str(row.get(name_col, "")).strip() if name_col else "",
                "tags": str(row.get(tags_col, "")).strip() if tags_col else "",
            }
        )
    return pd.DataFrame(rows)


class ActivationOutreachLookup:
    """Resolve outreach flags by publisher/creator id or normalized creator name."""

    def __init__(
        self,
        *,
        by_creator_id: dict[str, dict[str, bool]],
        by_publisher_id: dict[str, dict[str, bool]],
        by_name: dict[str, dict[str, bool]],
        flag_names: tuple[str, ...],
    ) -> None:
        self.by_creator_id = by_creator_id
        self.by_publisher_id = by_publisher_id
        self.by_name = by_name
        self.flag_names = flag_names

    def flags_for(self, *, creator_id: str = "", publisher_id: str = "", creator_name: str = "") -> dict[str, bool]:
        cid = _norm_id(creator_id) or _norm_id(publisher_id)
        pid = _norm_id(publisher_id) or _norm_id(creator_id)
        name_key = _norm_name(creator_name)
        found: dict[str, bool] | None = None
        if cid and cid in self.by_creator_id:
            found = self.by_creator_id[cid]
        elif pid and pid in self.by_publisher_id:
            found = self.by_publisher_id[pid]
        elif name_key and name_key in self.by_name:
            found = self.by_name[name_key]
        return {name: bool(found.get(name, False)) if found else False for name in self.flag_names}


def build_activation_outreach_lookup(
    *labeled_sources: tuple[str, str | Path | pd.DataFrame],
) -> ActivationOutreachLookup:
    """Build id/name resolvers from one or more outreach CSVs with boolean column names."""
    flag_names = tuple(label for label, _ in labeled_sources)
    by_creator_id: dict[str, dict[str, bool]] = {}
    by_publisher_id: dict[str, dict[str, bool]] = {}
    by_name: dict[str, dict[str, bool]] = {}

    def _mark(store: dict[str, dict[str, bool]], key: str, flag: str) -> None:
        if not key:
            return
        store.setdefault(key, {})
        store[key][flag] = True

    for flag, source in labeled_sources:
        frame = parse_activation_outreach_csv(source)
        for _, row in frame.iterrows():
            cid = row["creator_id"]
            pid = row["publisher_id"]
            name_key = _norm_name(row["creator_name"])
            if cid:
                _mark(by_creator_id, cid, flag)
            if pid:
                _mark(by_publisher_id, pid, flag)
                if not cid:
                    _mark(by_creator_id, pid, flag)
            if name_key:
                _mark(by_name, name_key, flag)

    return ActivationOutreachLookup(
        by_creator_id=by_creator_id,
        by_publisher_id=by_publisher_id,
        by_name=by_name,
        flag_names=flag_names,
    )


def attach_outreach_flags_to_creators(
    creator_table: pd.DataFrame,
    lookup: ActivationOutreachLookup | None,
) -> pd.DataFrame:
    """Add outreach boolean columns using publisher id + creator name matching."""
    out = creator_table.copy()
    if lookup is None or not lookup.flag_names:
        return out
    for flag in lookup.flag_names:
        out[flag] = False
    if creator_table.empty:
        return out

    for idx, row in creator_table.iterrows():
        flags = lookup.flags_for(
            creator_id=_norm_id(row.get("creator_id")),
            publisher_id=_norm_id(row.get("publisher_id", row.get("creator_id"))),
            creator_name=str(row.get("creator_name", "")),
        )
        for flag, value in flags.items():
            out.at[idx, flag] = value
    return out


def summarize_background_selection_flags(content: pd.DataFrame) -> pd.DataFrame:
    """Per creator: Jul–Sep (and ever-before-Oct) selection used only as background context."""
    from creatoriq_dashboard.boosting_scorecard import _eligible_content, normalize_content_raw

    eligible = _eligible_content(normalize_content_raw(content))
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "creator_id",
                "creator_name",
                "ever_selected_before_oct",
                "ever_selected_jul_sep",
                "first_selection_month",
                "selected_posts_jul_sep",
                "selected_posts_before_oct",
            ]
        )

    oct_start = pd.Timestamp("2026-10-01", tz="UTC")
    jul_sep_months = {"2026-07", "2026-08", "2026-09"}

    rows: list[dict] = []
    for creator_id, grp in eligible.groupby("creator_id"):
        name = next((str(v) for v in grp["creator_name"] if str(v).strip() not in {"", "nan"}), "")
        sel = grp[grp["selected"]]
        sel_before_oct = sel[sel["post_date"] < oct_start] if "post_date" in sel.columns else sel
        sel_jul_sep = sel[sel["month"].isin(jul_sep_months)] if "month" in sel.columns else sel.iloc[0:0]

        first_month = None
        if not sel.empty and "month" in sel.columns:
            months = sorted(m for m in sel["month"].dropna().unique())
            first_month = months[0] if months else None

        rows.append(
            {
                "creator_id": creator_id,
                "creator_name": name,
                "ever_selected_before_oct": len(sel_before_oct) > 0,
                "ever_selected_jul_sep": len(sel_jul_sep) > 0,
                "first_selection_month": first_month,
                "selected_posts_jul_sep": int(len(sel_jul_sep)),
                "selected_posts_before_oct": int(len(sel_before_oct)),
            }
        )

    return pd.DataFrame(rows)


def build_sep_to_oct_halo_detail(
    content: pd.DataFrame,
    *,
    outreach_lookup: ActivationOutreachLookup | None = None,
) -> pd.DataFrame:
    """Creator-level Sep→Oct halo rows: posting outcome + outreach + prior selection (Jul–Sep background)."""
    from creatoriq_dashboard.boosting_scorecard import _eligible_content, normalize_content_raw
    from creatoriq_dashboard.boosting_selection_impact import _period_bounds

    eligible = _eligible_content(normalize_content_raw(content))
    if eligible.empty:
        return pd.DataFrame()

    sep_start, sep_end = _period_bounds("2026-09-01", "2026-09-30")
    oct_start, oct_end = _period_bounds("2026-10-01", "2026-10-31")

    background = summarize_background_selection_flags(content)
    background = background.set_index("creator_id")

    sep_posts = eligible[(eligible["post_date"] >= sep_start) & (eligible["post_date"] <= sep_end)]
    oct_posts = eligible[(eligible["post_date"] >= oct_start) & (eligible["post_date"] <= oct_end)]

    sep_active = set(sep_posts["creator_id"].unique())
    oct_active = set(oct_posts["creator_id"].unique())

    sep_selected = (
        sep_posts.groupby("creator_id")["selected"].sum().astype(int) if not sep_posts.empty else pd.Series(dtype=int)
    )
    oct_selected = (
        oct_posts.groupby("creator_id")["selected"].sum().astype(int) if not oct_posts.empty else pd.Series(dtype=int)
    )

    creator_ids = sorted(sep_active | oct_active | set(background.index))
    rows: list[dict] = []
    for cid in creator_ids:
        name = ""
        if cid in background.index:
            name = str(background.loc[cid, "creator_name"])
        grp = eligible[eligible["creator_id"] == cid]
        if not grp.empty and not name:
            name = next((str(v) for v in grp["creator_name"] if str(v).strip() not in {"", "nan"}), "")

        active_sep = cid in sep_active
        active_oct = cid in oct_active
        if active_sep:
            cohort = "September active"
        elif active_oct:
            cohort = "October-only reactivation"
        else:
            continue

        rows.append(
            {
                "creator_id": cid,
                "creator_name": name,
                "cohort": cohort,
                "active_september": active_sep,
                "active_october": active_oct,
                "continued_sep_to_oct": active_sep and active_oct,
                "fell_off_sep_to_oct": active_sep and not active_oct,
                "reactivated_oct_not_sep": (not active_sep) and active_oct,
                "selected_eligible_posts_september": int(sep_selected.get(cid, 0)),
                "selected_eligible_posts_october": int(oct_selected.get(cid, 0)),
                "had_selection_in_september": int(sep_selected.get(cid, 0)) > 0,
                "had_selection_in_october": int(oct_selected.get(cid, 0)) > 0,
            }
        )

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail

    bg_cols = [
        "ever_selected_before_oct",
        "ever_selected_jul_sep",
        "first_selection_month",
        "selected_posts_jul_sep",
        "selected_posts_before_oct",
    ]
    detail = detail.merge(
        background.reset_index()[["creator_id", *bg_cols]],
        on="creator_id",
        how="left",
    )
    for col in bg_cols:
        if col.startswith("ever_"):
            detail[col] = detail[col].fillna(False).astype(bool)
        elif col == "first_selection_month":
            detail[col] = detail[col].astype(object).where(detail[col].notna(), None)
        else:
            detail[col] = detail[col].fillna(0).astype(int)

    if outreach_lookup is not None:
        detail = attach_outreach_flags_to_creators(detail, outreach_lookup)

    return detail.sort_values(
        ["fell_off_sep_to_oct", "continued_sep_to_oct", "creator_name"],
        ascending=[False, False, True],
    )


def summarize_sep_to_oct_retention_by_factors(detail: pd.DataFrame) -> pd.DataFrame:
    """Retention rates for Sep actives, split by outreach and Jul–Sep selection background."""
    if detail.empty:
        return pd.DataFrame(
            columns=["factor", "segment", "sep_actives", "continued_in_oct", "continuation_rate"]
        )

    sep = detail[detail["active_september"]].copy()
    rows: list[dict] = []

    def _add(factor: str, segment: str, mask: pd.Series) -> None:
        sub = sep[mask]
        if sub.empty:
            return
        continued = int(sub["continued_sep_to_oct"].sum())
        rows.append(
            {
                "factor": factor,
                "segment": segment,
                "sep_actives": len(sub),
                "continued_in_oct": continued,
                "fell_off_oct": len(sub) - continued,
                "continuation_rate": continued / len(sub),
            }
        )

    _add("All September actives", "All", pd.Series(True, index=sep.index))

    _add("Selection in September", "Yes", sep["had_selection_in_september"])
    _add("Selection in September", "No", ~sep["had_selection_in_september"])
    _add("Ever selected Jul–Sep (background)", "Yes", sep["ever_selected_jul_sep"])
    _add("Ever selected Jul–Sep (background)", "No", ~sep["ever_selected_jul_sep"])
    _add("Ever selected before October", "Yes", sep["ever_selected_before_oct"])
    _add("Ever selected before October", "No", ~sep["ever_selected_before_oct"])

    outreach_cols = [c for c in sep.columns if c.endswith("_outreach")]
    for col in outreach_cols:
        pretty = col.replace("_", " ").title()
        _add(pretty, "Yes — on outreach list", sep[col].astype(bool))
        _add(pretty, "No — not on list", ~sep[col].astype(bool))
        _add(f"{pretty} × Sep selection", "Outreach + selected in Sep", sep[col].astype(bool) & sep["had_selection_in_september"])
        _add(
            f"{pretty} × Sep selection",
            "Outreach + not selected in Sep",
            sep[col].astype(bool) & ~sep["had_selection_in_september"],
        )

    # Oct-only reactivations (not active in Sep)
    oct_only = detail[detail["reactivated_oct_not_sep"]]
    if not oct_only.empty:
        for col in outreach_cols:
            on_list = oct_only[oct_only[col].astype(bool)]
            if on_list.empty:
                continue
            pretty = col.replace("_", " ").title()
            rows.append(
                {
                    "factor": f"{pretty} (reactivated Oct, not Sep active)",
                    "segment": "On outreach list",
                    "sep_actives": 0,
                    "continued_in_oct": len(on_list),
                    "fell_off_oct": 0,
                    "continuation_rate": None,
                }
            )

    return pd.DataFrame(rows)


def build_activation_outreach_outcomes(
    content: pd.DataFrame,
    lookup: ActivationOutreachLookup | None,
) -> pd.DataFrame:
    """Creators on activation lists: eligible posting in Sep/Oct (not limited to Sep actives)."""
    from creatoriq_dashboard.boosting_scorecard import _eligible_content, normalize_content_raw

    if lookup is None or not lookup.flag_names:
        return pd.DataFrame()

    eligible = _eligible_content(normalize_content_raw(content))
    if eligible.empty:
        return pd.DataFrame()

    background = summarize_background_selection_flags(content).set_index("creator_id")

    rows: list[dict] = []
    for creator_id, grp in eligible.groupby("creator_id"):
        name = next((str(v) for v in grp["creator_name"] if str(v).strip() not in {"", "nan"}), "")
        flags = lookup.flags_for(creator_id=_norm_id(creator_id), creator_name=name)
        if not any(flags.values()):
            continue

        row: dict = {
            "creator_id": creator_id,
            "creator_name": name,
            "eligible_posts_total": int(len(grp)),
            "eligible_posts_september": int((grp["month"] == "2026-09").sum()),
            "eligible_posts_october": int((grp["month"] == "2026-10").sum()),
            "active_september": bool((grp["month"] == "2026-09").any()),
            "active_october": bool((grp["month"] == "2026-10").any()),
            "had_selection_jul_sep": False,
            "ever_selected_before_oct": False,
        }
        row.update(flags)
        if creator_id in background.index:
            bg = background.loc[creator_id]
            row["had_selection_jul_sep"] = bool(bg["ever_selected_jul_sep"])
            row["ever_selected_before_oct"] = bool(bg["ever_selected_before_oct"])
            row["first_selection_month"] = bg.get("first_selection_month")
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["active_october", "active_september"], ascending=False)
