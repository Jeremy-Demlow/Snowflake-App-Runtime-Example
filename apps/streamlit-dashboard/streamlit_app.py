"""
Ski Resort — Daily KPIs (Streamlit in Snowflake)

The Streamlit twin of the Next.js dashboard. It renders the SAME read-only daily
resort KPIs over the SAME data, deployed through the SAME workflow
(`snow streamlit deploy`). The point of the template is that one simple loop
ships either framework.

Auth:
  * In Snowflake (deployed): st.connection uses the app's embedded identity.
  * Locally (`streamlit run`): set SNOWFLAKE_DEFAULT_CONNECTION_NAME to your
    connection; st.connection reads ~/.snowflake/connections.toml.

All SQL is READ-ONLY and fully qualified with the demo database, so it runs under
the SKI_READONLY role and does not depend on a default database/schema.
"""
import altair as alt
import pandas as pd
import streamlit as st

BRAND = "#29b5e8"
BRAND_DARK = "#0a2f5a"

st.set_page_config(page_title="Ski Resort — Daily KPIs", page_icon="⛷️", layout="wide")

# st.connection("snowflake") resolves the connection from
# SNOWFLAKE_DEFAULT_CONNECTION_NAME (local) or the app's embedded identity (SiS).
conn = st.connection("snowflake")

# One read-only data copy is shared by every environment, so the database is a
# single fixed value. Dev and prod app instances read the same data and differ
# only by which schema/app object they deploy into (APPS vs APPS_DEV).
DEMO_DB = "SKI_RESORT_DEMO"
FACT = f"{DEMO_DB}.MARTS.FACT_PASS_USAGE"
DIM_DATE = f"{DEMO_DB}.MARTS.DIM_DATE"
DIM_CUSTOMER = f"{DEMO_DB}.MARTS.DIM_CUSTOMER"
LATEST_SEASON = (
    f"(SELECT MAX(d.ski_season) FROM {FACT} pu "
    f"JOIN {DIM_DATE} d ON pu.date_key = d.date_key)"
)


@st.cache_data(ttl=600)
def q(sql: str) -> pd.DataFrame:
    return conn.query(sql, ttl=600)


# ---- Queries (identical logic to the Next.js app) -------------------------
def load_kpis() -> pd.Series:
    df = q(
        f"""
        SELECT
          {LATEST_SEASON} AS ski_season,
          COUNT(*) AS total_visits,
          COUNT(DISTINCT pu.customer_key) AS unique_visitors,
          ROUND(AVG(pu.hours_on_mountain), 2) AS avg_hours_per_visit,
          ROUND(100 * COUNT_IF(c.is_pass_holder) / NULLIF(COUNT(*), 0), 1) AS pass_holder_pct,
          ROUND(100 * COUNT_IF(d.is_weekend) / NULLIF(COUNT(*), 0), 1) AS weekend_share_pct
        FROM {FACT} pu
        JOIN {DIM_DATE} d ON pu.date_key = d.date_key
        JOIN {DIM_CUSTOMER} c ON pu.customer_key = c.customer_key
        WHERE d.ski_season = {LATEST_SEASON}
        """
    )
    return df.iloc[0]


def load_by_season() -> pd.DataFrame:
    return q(
        f"""
        SELECT d.ski_season AS season,
               COUNT(*) AS visits,
               COUNT(DISTINCT pu.customer_key) AS unique_visitors
        FROM {FACT} pu
        JOIN {DIM_DATE} d ON pu.date_key = d.date_key
        GROUP BY d.ski_season
        ORDER BY d.ski_season
        """
    )


def load_by_day() -> pd.DataFrame:
    return q(
        f"""
        SELECT d.day_name AS day,
               COUNT(*) AS visits,
               MIN(DAYOFWEEKISO(d.full_date)) AS ord
        FROM {FACT} pu
        JOIN {DIM_DATE} d ON pu.date_key = d.date_key
        WHERE d.ski_season = {LATEST_SEASON}
        GROUP BY d.day_name
        ORDER BY ord
        """
    )


def load_by_snow() -> pd.DataFrame:
    return q(
        f"""
        SELECT d.snow_condition AS condition,
               COUNT(*) AS visits,
               ROUND(AVG(pu.hours_on_mountain), 2) AS avg_hours
        FROM {FACT} pu
        JOIN {DIM_DATE} d ON pu.date_key = d.date_key
        WHERE d.ski_season = {LATEST_SEASON}
        GROUP BY d.snow_condition
        ORDER BY visits DESC
        """
    )


def load_trend() -> pd.DataFrame:
    return q(
        f"""
        SELECT d.full_date AS day,
               COUNT(*) AS visits
        FROM {FACT} pu
        JOIN {DIM_DATE} d ON pu.date_key = d.date_key
        WHERE d.ski_season = {LATEST_SEASON}
        GROUP BY d.full_date
        ORDER BY d.full_date
        """
    )


# ---- Layout ---------------------------------------------------------------
try:
    kpis = load_kpis()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load resort data from {DEMO_DB}.MARTS: {exc}")
    st.caption(
        f"Check that the active role has SELECT on {DEMO_DB}.MARTS."
    )
    st.stop()

season = kpis["SKI_SEASON"]

st.title("Daily Resort KPIs")
st.caption(f"Visitation and guest activity for season {season} · source {DEMO_DB}.MARTS")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total visits", f"{int(kpis['TOTAL_VISITS']):,}")
c2.metric("Unique visitors", f"{int(kpis['UNIQUE_VISITORS']):,}")
c3.metric("Avg hours / visit", f"{kpis['AVG_HOURS_PER_VISIT']:.1f} h")
c4.metric("Pass-holder share", f"{kpis['PASS_HOLDER_PCT']:.1f}%")
c5.metric("Weekend share", f"{kpis['WEEKEND_SHARE_PCT']:.1f}%")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Visits by ski season")
    by_season = load_by_season().melt(
        id_vars="SEASON", value_vars=["VISITS", "UNIQUE_VISITORS"],
        var_name="metric", value_name="count",
    )
    chart = (
        alt.Chart(by_season)
        .mark_bar()
        .encode(
            x=alt.X("SEASON:N", title=None),
            y=alt.Y("count:Q", title=None),
            color=alt.Color(
                "metric:N",
                scale=alt.Scale(domain=["VISITS", "UNIQUE_VISITORS"], range=[BRAND, BRAND_DARK]),
                title=None,
            ),
            xOffset="metric:N",
        )
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)

with right:
    st.subheader(f"Visits by day of week · {season}")
    by_day = load_by_day()
    chart = (
        alt.Chart(by_day)
        .mark_bar(color=BRAND)
        .encode(
            x=alt.X("DAY:N", sort=alt.SortField("ORD"), title=None),
            y=alt.Y("VISITS:Q", title=None),
        )
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)

left2, right2 = st.columns(2)

with left2:
    st.subheader("Visits by snow condition")
    by_snow = load_by_snow()
    chart = (
        alt.Chart(by_snow)
        .mark_bar(color=BRAND)
        .encode(
            x=alt.X("VISITS:Q", title=None),
            y=alt.Y("CONDITION:N", sort="-x", title=None),
        )
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)

with right2:
    st.subheader(f"Daily visits trend · {season}")
    trend = load_trend()
    chart = (
        alt.Chart(trend)
        .mark_line(color=BRAND)
        .encode(
            x=alt.X("DAY:T", title=None),
            y=alt.Y("VISITS:Q", title=None),
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)
