"""Evidence providers for the SDK BI triangulation loop."""
from __future__ import annotations

import re
from io import StringIO

import pandas as pd
import snowflake.connector

try:
    from .agent_client import call_cortex_agent
    from .evidence import EvidenceResult, EvidenceStep
except ImportError:
    from agent_client import call_cortex_agent
    from evidence import EvidenceResult, EvidenceStep


def _connect(connection: str):
    return snowflake.connector.connect(connection_name=connection)


def _query_df(connection: str, sql: str) -> pd.DataFrame:
    conn = _connect(connection)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=cols)


def _csv_preview(df: pd.DataFrame, rows: int = 8) -> str:
    if df is None or df.empty:
        return "No rows returned."
    return df.head(rows).to_csv(index=False)


def _semantic_sql(target: str) -> tuple[str, str]:
    name = target.split(".")[-1].upper()
    if name == "SEM_REVENUE":
        sql = f"""
SELECT *
FROM SEMANTIC_VIEW(
  {target}
  METRICS ticket_revenue, rental_revenue, fnb_revenue
  DIMENSIONS full_date
)
ORDER BY full_date DESC
LIMIT 14
""".strip()
        return sql, "Recent revenue by source from SEM_REVENUE."
    if name == "SEM_DAILY_SUMMARY":
        sql = f"""
SELECT *
FROM SEMANTIC_VIEW(
  {target}
  METRICS total_visits
  DIMENSIONS full_date, day_name
)
ORDER BY full_date DESC
LIMIT 14
""".strip()
        return sql, "Recent visitation context from SEM_DAILY_SUMMARY."
    if name == "SEM_WEATHER_ANALYTICS":
        sql = f"""
SELECT *
FROM SEMANTIC_VIEW(
  {target}
  METRICS total_snowfall, powder_day_count
  DIMENSIONS full_date
)
ORDER BY full_date DESC
LIMIT 14
""".strip()
        return sql, "Recent snow / powder context from SEM_WEATHER_ANALYTICS."
    if name == "SEM_MARKETING_ANALYTICS":
        sql = f"""
SELECT *
FROM SEMANTIC_VIEW(
  {target}
  METRICS total_conversions, total_revenue
  DIMENSIONS full_date, campaign_channel
)
ORDER BY full_date DESC
LIMIT 20
""".strip()
        return sql, "Recent marketing context from SEM_MARKETING_ANALYTICS."
    sql = f"SELECT * FROM SEMANTIC_VIEW({target}) LIMIT 20"
    return sql, f"Generic semantic view sample from {target}."


def run_semantic_provider(step: EvidenceStep, connection: str) -> EvidenceResult:
    sql, desc = _semantic_sql(step.target)
    try:
        df = _query_df(connection, sql)
        text = f"{desc}\n\n{_csv_preview(df)}"
        confidence = 0.82 if not df.empty else 0.35
        return EvidenceResult(
            provider="semantic_view",
            target=step.target,
            purpose=step.purpose,
            text=text,
            sql=[sql],
            dataframe=df,
            confidence=confidence,
            trace=[{"event": "semantic_query", "target": step.target, "rows": len(df)}],
        )
    except Exception as exc:
        return EvidenceResult(
            provider="semantic_view",
            target=step.target,
            purpose=step.purpose,
            errors=[str(exc)],
            confidence=0.0,
            trace=[{"event": "semantic_error", "target": step.target, "error": str(exc)}],
        )


def _raw_revenue_sql() -> str:
    return """
WITH max_revenue_date AS (
  SELECT MAX(full_date) AS max_full_date
  FROM (
    SELECT d.full_date
    FROM SKI_RESORT_DEMO.MARTS.FACT_TICKET_SALES t
    JOIN SKI_RESORT_DEMO.MARTS.DIM_DATE d ON d.date_key = t.purchase_date_key
    UNION ALL
    SELECT d.full_date
    FROM SKI_RESORT_DEMO.MARTS.FACT_RENTALS r
    JOIN SKI_RESORT_DEMO.MARTS.DIM_DATE d ON d.date_key = r.rental_date_key
    UNION ALL
    SELECT d.full_date
    FROM SKI_RESORT_DEMO.MARTS.FACT_FOOD_BEVERAGE f
    JOIN SKI_RESORT_DEMO.MARTS.DIM_DATE d ON d.date_key = f.transaction_date_key
  )
), recent_dates AS (
  SELECT date_key, full_date
  FROM SKI_RESORT_DEMO.MARTS.DIM_DATE
  WHERE full_date <= (SELECT max_full_date FROM max_revenue_date)
  ORDER BY full_date DESC
  LIMIT 14
), ticket AS (
  SELECT d.full_date, SUM(t.purchase_amount) AS ticket_revenue
  FROM recent_dates d
  LEFT JOIN SKI_RESORT_DEMO.MARTS.FACT_TICKET_SALES t
    ON t.purchase_date_key = d.date_key
  GROUP BY d.full_date
), rentals AS (
  SELECT d.full_date, SUM(r.rental_amount) AS rental_revenue
  FROM recent_dates d
  LEFT JOIN SKI_RESORT_DEMO.MARTS.FACT_RENTALS r
    ON r.rental_date_key = d.date_key
  GROUP BY d.full_date
), fnb AS (
  SELECT d.full_date, SUM(f.total_amount) AS fnb_revenue
  FROM recent_dates d
  LEFT JOIN SKI_RESORT_DEMO.MARTS.FACT_FOOD_BEVERAGE f
    ON f.transaction_date_key = d.date_key
  GROUP BY d.full_date
)
SELECT
  d.full_date,
  COALESCE(t.ticket_revenue, 0) AS ticket_revenue,
  COALESCE(r.rental_revenue, 0) AS rental_revenue,
  COALESCE(f.fnb_revenue, 0) AS fnb_revenue,
  COALESCE(t.ticket_revenue, 0) + COALESCE(r.rental_revenue, 0) + COALESCE(f.fnb_revenue, 0) AS total_revenue
FROM recent_dates d
LEFT JOIN ticket t ON t.full_date = d.full_date
LEFT JOIN rentals r ON r.full_date = d.full_date
LEFT JOIN fnb f ON f.full_date = d.full_date
ORDER BY d.full_date DESC
""".strip()


_WRITE_SQL_RE = re.compile(
    r"\b(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|MERGE|TRUNCATE|COPY|GRANT|REVOKE|REPLACE|RENAME|UNDROP)\b",
    re.IGNORECASE,
)


def run_governed_sql(step: EvidenceStep, connection: str) -> EvidenceResult:
    sql = _raw_revenue_sql() if step.prompt_or_query == "revenue_recent_sanity" else step.prompt_or_query
    if _WRITE_SQL_RE.search(sql):
        return EvidenceResult(
            provider="sql",
            target=step.target,
            purpose=step.purpose,
            errors=["Blocked non-read-only SQL."],
            confidence=0.0,
        )
    try:
        df = _query_df(connection, sql)
        return EvidenceResult(
            provider="sql",
            target=step.target,
            purpose=step.purpose,
            text=f"Raw table sanity check.\n\n{_csv_preview(df)}",
            sql=[sql],
            dataframe=df,
            confidence=0.75 if not df.empty else 0.3,
            trace=[{"event": "sql_query", "target": step.target, "rows": len(df)}],
        )
    except Exception as exc:
        return EvidenceResult(
            provider="sql",
            target=step.target,
            purpose=step.purpose,
            errors=[str(exc)],
            confidence=0.0,
            trace=[{"event": "sql_error", "target": step.target, "error": str(exc)}],
        )


def run_agent_provider(step: EvidenceStep, connection: str, on_event=None) -> EvidenceResult:
    events: list[dict] = []
    def _on_event(event: str, data: dict) -> None:
        events.append({"event": event, "data": data})
        if on_event is not None:
            on_event(event, data)
    resp = call_cortex_agent(
        step.prompt_or_query,
        agent_fqn=step.target,
        connection=connection,
        on_event=_on_event,
        timeout=60,
    )
    df = resp.dataframes[0] if resp.dataframes else None
    # The agent often self-corrects: an internal sub-query can fail and be
    # retried, leaving non-fatal entries in resp.errors even though the final
    # answer is sound. Only treat the agent as failed when it produced no
    # usable answer text.
    has_answer = bool(resp.text and resp.text.strip())
    fatal_errors = [] if has_answer else list(resp.errors)
    if has_answer:
        confidence = 0.85
    elif resp.errors:
        confidence = 0.2
    else:
        confidence = 0.4
    return EvidenceResult(
        provider="agent",
        target=step.target,
        purpose=step.purpose,
        text=resp.text,
        sql=resp.sql_queries,
        dataframe=df,
        charts=resp.chart_specs,
        trace=(
            [{"event": "agent_status", "statuses": resp.statuses,
              "ttfb": resp.time_to_first_byte,
              "self_corrected": bool(resp.errors) and has_answer,
              "internal_errors": resp.errors}]
            + events[:20]
        ),
        errors=fatal_errors,
        confidence=confidence,
    )


def run_process_provider(step: EvidenceStep, connection: str) -> EvidenceResult:
    return EvidenceResult(
        provider="process",
        target=step.target,
        purpose=step.purpose,
        text="Process context is available in the Streamlit app and semantic YAML definitions. Use the Trace tab for scoped files.",
        confidence=0.5,
        trace=[{"event": "process_context", "target": step.target}],
    )


def run_provider(step: EvidenceStep, connection: str, on_event=None) -> EvidenceResult:
    if step.provider == "semantic_view":
        return run_semantic_provider(step, connection)
    if step.provider == "sql":
        return run_governed_sql(step, connection)
    if step.provider == "agent":
        return run_agent_provider(step, connection, on_event=on_event)
    return run_process_provider(step, connection)
