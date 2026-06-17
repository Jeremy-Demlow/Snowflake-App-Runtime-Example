"""Reconcile multiple evidence results into one BI answer."""
from __future__ import annotations

import pandas as pd

try:
    from .evidence import BIAnswer, EvidenceResult, PromptIntent
except ImportError:
    from evidence import BIAnswer, EvidenceResult, PromptIntent


def _usd(value: float) -> str:
    """Currency text that will not trigger Markdown/LaTeX parsing."""
    return f"USD {value:,.0f}"


def _latest_revenue_summary(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    cols = {c.upper(): c for c in df.columns}
    date_col = cols.get("FULL_DATE")
    total_col = cols.get("TOTAL_REVENUE")
    if total_col is None:
        revenue_cols = [cols.get(n) for n in ("TICKET_REVENUE", "RENTAL_REVENUE", "FNB_REVENUE")]
        revenue_cols = [c for c in revenue_cols if c]
        if revenue_cols:
            values = df[revenue_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
            total = values.sum(axis=1)
        else:
            return None
    else:
        total = pd.to_numeric(df[total_col], errors="coerce").fillna(0)
    if total.empty:
        return None
    latest = total.iloc[0]
    prior = total.iloc[1:4].mean() if len(total) > 1 else 0
    if prior:
        pct = ((latest - prior) / prior) * 100
        date = f" on {df[date_col].iloc[0]}" if date_col else ""
        direction = "up" if pct >= 0 else "down"
        return f"Latest available revenue{date} is {direction} {abs(pct):.1f}% versus the prior 3-day average ({_usd(latest)} vs {_usd(prior)})."
    return f"Latest available revenue is {_usd(latest)}."


def _component_driver_summary(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    cols = {c.upper(): c for c in df.columns}
    components = [
        ("ticket revenue", cols.get("TICKET_REVENUE")),
        ("rental revenue", cols.get("RENTAL_REVENUE")),
        ("F&B revenue", cols.get("FNB_REVENUE")),
    ]
    deltas: list[tuple[str, float, float, float]] = []
    for label, col in components:
        if not col or len(df) < 2:
            continue
        series = pd.to_numeric(df[col], errors="coerce").fillna(0)
        latest = float(series.iloc[0])
        prior = float(series.iloc[1:4].mean()) if len(series) > 1 else 0.0
        deltas.append((label, latest - prior, latest, prior))
    if not deltas:
        return None
    deltas.sort(key=lambda x: x[1], reverse=True)
    positive = [d for d in deltas if d[1] > 0]
    if not positive:
        leader = deltas[-1]
        return f"No revenue component increased versus the prior 3-day average; the least negative component was {leader[0]}."
    leader = positive[0]
    pieces = [f"{label} (+{_usd(delta)})" for label, delta, _latest, _prior in positive[:3]]
    return f"The clearest driver is {leader[0]}, with component lift versus the prior 3-day average: {', '.join(pieces)}."


def _visitation_summary(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    cols = {c.upper(): c for c in df.columns}
    visits_col = cols.get("TOTAL_VISITS")
    date_col = cols.get("FULL_DATE")
    if not visits_col or len(df) < 2:
        return None
    visits = pd.to_numeric(df[visits_col], errors="coerce").fillna(0)
    latest = float(visits.iloc[0])
    prior = float(visits.iloc[1:4].mean())
    if not prior:
        return None
    pct = ((latest - prior) / prior) * 100
    date = f" on {df[date_col].iloc[0]}" if date_col else ""
    return f"Visitation{date} was {'up' if pct >= 0 else 'down'} {abs(pct):.1f}% versus the prior 3-day average ({latest:,.0f} vs {prior:,.0f} visits)."


def _weather_summary(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    cols = {c.upper(): c for c in df.columns}
    snow_col = cols.get("TOTAL_SNOWFALL")
    powder_col = cols.get("POWDER_DAY_COUNT")
    if not snow_col and not powder_col:
        return None
    pieces = []
    if snow_col:
        snow = pd.to_numeric(df[snow_col], errors="coerce").fillna(0)
        pieces.append(f"snowfall was {float(snow.iloc[0]):.1f} inches equivalent on the latest date")
    if powder_col:
        powder = pd.to_numeric(df[powder_col], errors="coerce").fillna(0)
        pieces.append(f"powder-day count was {int(powder.iloc[0])}")
    return "Weather check: " + "; ".join(pieces) + "."


def reconcile(prompt: str, intent: PromptIntent, results: list[EvidenceResult]) -> BIAnswer:
    usable = [r for r in results if not r.errors]
    tables = [r.dataframe for r in usable if r.dataframe is not None and not r.dataframe.empty]
    charts = [chart for r in usable for chart in r.charts]

    lines: list[str] = []
    primary = usable[0] if usable else None

    if intent.domain == "revenue":
        revenue_result = next((r for r in usable if r.provider in ("semantic_view", "sql") and r.dataframe is not None), None)
        summary = _latest_revenue_summary(revenue_result.dataframe) if revenue_result else None
        if summary:
            lines.append(summary)
            component_summary = _component_driver_summary(revenue_result.dataframe)
            if component_summary:
                lines.append(component_summary)
        elif primary and primary.text:
            lines.append(primary.text.strip())
    elif primary and primary.text:
        lines.append(primary.text.strip())

    if intent.is_driver_question:
        supporting: list[str] = []
        for r in usable[1:]:
            if "WEATHER" in r.target.upper() and r.dataframe is not None and not r.dataframe.empty:
                weather = _weather_summary(r.dataframe)
                supporting.append(weather or "Weather context was checked for snowfall/powder-day contribution.")
            elif "DAILY_SUMMARY" in r.target.upper() and r.dataframe is not None and not r.dataframe.empty:
                visits = _visitation_summary(r.dataframe)
                supporting.append(visits or "Visitation/day-of-week context was checked against the revenue move.")
            elif r.provider == "sql" and r.dataframe is not None and not r.dataframe.empty:
                supporting.append("Raw fact-table revenue was used as a sanity check against the semantic layer.")
            elif r.provider == "agent" and r.text:
                supporting.append("The deployed resort agent was also checked for narrative synthesis; see Evidence for its full response.")
        if supporting:
            lines.append(" ".join(dict.fromkeys(supporting)))

    if not lines:
        if results:
            lines.append("I found evidence paths, but none returned a clean answer. Check the Trace tab for errors and next-best routes.")
        else:
            lines.append("I could not find a suitable evidence path for this question.")

    conflicts: list[str] = []
    confidence = "high" if len(usable) >= 2 and not conflicts else "medium"
    if any(r.errors for r in results):
        confidence = "medium" if usable else "low"

    return BIAnswer(
        text="\n\n".join(lines),
        evidence=results,
        tables=tables,
        charts=charts,
        conflicts=conflicts,
        confidence=confidence,
        route_summary=" -> ".join(r.provider for r in results) if results else "none",
    )
