"""Ski-resort KPI dashboard rendered against SKI_RESORT_DEMO.MARTS.*.

Uses real dbt mart tables: FACT_TICKET_SALES, FACT_LIFT_SCANS, DIM_LOCATION.
Falls back gracefully with a warning when marts are unreachable so the chat
demo still loads.
"""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    import snowflake.connector
except ImportError:  # pragma: no cover
    snowflake = None  # type: ignore


def _connection_name() -> str:
    return os.getenv("SNOWFLAKE_CONNECTION_NAME") or "myconnection"


def _database() -> str:
    return os.getenv("CC_DASHBOARD_DATABASE") or "SKI_RESORT_DEMO"


@st.cache_resource(show_spinner=False)
def _conn(connection_name: str):
    return snowflake.connector.connect(connection_name=connection_name)


@st.cache_data(ttl=300, show_spinner=False)
def _query(connection_name: str, sql: str) -> pd.DataFrame:
    cur = _conn(connection_name).cursor()
    try:
        cur.execute(sql)
        cols = [c[0].lower() for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        cur.close()


def reset_connection_cache() -> None:
    """Clear cached connector + query data after token expiry or role changes."""
    _conn.clear()
    _query.clear()


def _safe_query(sql: str, connection_name: str | None = None) -> pd.DataFrame | None:
    connection_name = connection_name or _connection_name()
    try:
        return _query(connection_name, sql)
    except Exception as exc:
        if "390114" in str(exc) or "token has expired" in str(exc).lower():
            reset_connection_cache()
            try:
                return _query(connection_name, sql)
            except Exception as retry_exc:
                exc = retry_exc
        st.warning(f"Query failed (showing placeholder): {exc}", icon=":material/warning:")
        return None


def render_dashboard(suppress_title: bool = False, connection_name: str | None = None) -> None:
    connection_name = connection_name or _connection_name()
    db = _database()
    if not suppress_title:
        st.title("Ski Resort — Gold KPIs")

    asof = _safe_query(
        f"SELECT MAX(purchase_date) AS asof FROM {db}.MARTS.FACT_TICKET_SALES",
        connection_name,
    )
    asof_date = asof["asof"][0] if asof is not None and not asof.empty else None
    asof_label = (
        f"as of {asof_date}" if asof_date else f"as of {datetime.now():%Y-%m-%d}"
    )
    st.caption(
        f"Source: `{db}.MARTS` · connection: `{connection_name}` · {asof_label}"
    )

    # Use the latest data date so synthetic datasets still surface real values.
    asof_filter = (
        f"DATE '{asof_date}'" if asof_date else "CURRENT_DATE()"
    )

    revenue_mtd = _safe_query(
        f"""
        SELECT COALESCE(SUM(purchase_amount), 0) AS revenue_mtd
        FROM {db}.MARTS.FACT_TICKET_SALES
        WHERE DATE_TRUNC('MONTH', purchase_date) = DATE_TRUNC('MONTH', {asof_filter})
        """,
        connection_name,
    )
    tickets_today = _safe_query(
        f"""
        SELECT COUNT(*) AS tickets_today
        FROM {db}.MARTS.FACT_TICKET_SALES
        WHERE purchase_date = {asof_filter}
        """,
        connection_name,
    )
    lift_scans_7d = _safe_query(
        f"""
        SELECT COUNT(*) AS scans_7d, AVG(wait_time_minutes) AS avg_wait_min
        FROM {db}.MARTS.FACT_LIFT_SCANS
        WHERE scan_timestamp >= DATEADD(day, -7, {asof_filter}::timestamp)
          AND scan_timestamp <  DATEADD(day,  1, {asof_filter}::timestamp)
        """,
        connection_name,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Revenue (current month)",
        f"${(revenue_mtd['revenue_mtd'][0] if revenue_mtd is not None else 0):,.0f}",
    )
    c2.metric(
        f"Tickets sold ({asof_date or 'today'})",
        f"{int(tickets_today['tickets_today'][0]) if tickets_today is not None else 0:,}",
    )
    if lift_scans_7d is not None and not lift_scans_7d.empty:
        avg_wait = lift_scans_7d["avg_wait_min"][0] or 0
        c3.metric(
            "Lift scans (last 7d of data)",
            f"{int(lift_scans_7d['scans_7d'][0]):,}",
            delta=f"avg wait {avg_wait:.1f} min",
            delta_color="off",
        )
    else:
        c3.metric("Lift scans (7d)", "–")

    st.subheader("Revenue trend — last 30 days")
    rev_30 = _safe_query(
        f"""
        SELECT purchase_date, SUM(purchase_amount) AS revenue
        FROM {db}.MARTS.FACT_TICKET_SALES
        WHERE purchase_date >= DATEADD(day, -30, {asof_filter})
        GROUP BY 1
        ORDER BY 1
        """,
        connection_name,
    )
    if rev_30 is not None and not rev_30.empty:
        st.line_chart(rev_30.set_index("purchase_date")["revenue"])
    else:
        st.info("No revenue data available.")

    st.subheader("Revenue by location (last 30 days)")
    rev_loc = _safe_query(
        f"""
        SELECT l.location_name, SUM(f.purchase_amount) AS revenue
        FROM {db}.MARTS.FACT_TICKET_SALES f
        JOIN {db}.MARTS.DIM_LOCATION l USING (location_key)
        WHERE f.purchase_date >= DATEADD(day, -30, {asof_filter})
        GROUP BY 1
        ORDER BY 2 DESC
        """,
        connection_name,
    )
    if rev_loc is not None and not rev_loc.empty:
        st.bar_chart(rev_loc.set_index("location_name")["revenue"])
    else:
        st.info("No per-location breakdown available.")
