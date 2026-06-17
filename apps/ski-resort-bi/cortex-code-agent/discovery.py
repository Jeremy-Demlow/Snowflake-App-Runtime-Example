"""Fast metadata scouts for BI evidence discovery."""
from __future__ import annotations

from pathlib import Path

import snowflake.connector

try:
    from .evidence import AgentAsset, DiscoveryResult, ProcessAsset, SemanticAsset, TableAsset
    from .policy import SKI_RESORT_DATABASE, SKI_RESORT_SEMANTIC_SCHEMA
except ImportError:  # standalone import from test harnesses
    from evidence import AgentAsset, DiscoveryResult, ProcessAsset, SemanticAsset, TableAsset
    from policy import SKI_RESORT_DATABASE, SKI_RESORT_SEMANTIC_SCHEMA


REPO_ROOT = Path(__file__).resolve().parent.parent


def _rows_as_dicts(cur) -> list[dict]:
    cols = [c[0].lower() for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _connect(connection: str):
    return snowflake.connector.connect(connection_name=connection)


def discover_agents(connection: str, database: str = SKI_RESORT_DATABASE) -> list[AgentAsset]:
    conn = _connect(connection)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW AGENTS IN DATABASE {database}")
            rows = _rows_as_dicts(cur)
    finally:
        conn.close()
    assets: list[AgentAsset] = []
    for row in rows:
        name = row.get("name") or ""
        schema = row.get("schema_name") or ""
        db = row.get("database_name") or database
        assets.append(AgentAsset(
            fqn=f"{db}.{schema}.{name}",
            name=name,
            comment=row.get("comment") or "",
        ))
    return assets


def discover_semantic_views(
    connection: str,
    database: str = SKI_RESORT_DATABASE,
) -> list[SemanticAsset]:
    conn = _connect(connection)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW SEMANTIC VIEWS IN DATABASE {database}")
            rows = _rows_as_dicts(cur)
    finally:
        conn.close()
    assets: list[SemanticAsset] = []
    for row in rows:
        name = row.get("name") or ""
        schema = row.get("schema_name") or SKI_RESORT_SEMANTIC_SCHEMA
        db = row.get("database_name") or database
        assets.append(SemanticAsset(
            fqn=f"{db}.{schema}.{name}",
            name=name,
            schema=schema,
            comment=row.get("comment") or "",
        ))
    return assets


def discover_tables(connection: str, database: str = SKI_RESORT_DATABASE, schema: str = "MARTS") -> list[TableAsset]:
    conn = _connect(connection)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW TABLES IN SCHEMA {database}.{schema}")
            rows = _rows_as_dicts(cur)
    finally:
        conn.close()
    assets: list[TableAsset] = []
    for row in rows:
        name = row.get("name") or ""
        sch = row.get("schema_name") or schema
        db = row.get("database_name") or database
        assets.append(TableAsset(
            fqn=f"{db}.{sch}.{name}",
            name=name,
            schema=sch,
            kind=row.get("kind") or "TABLE",
        ))
    return assets


def discover_process_context(prompt: str) -> list[ProcessAsset]:
    lower = prompt.lower()
    candidates: list[ProcessAsset] = []
    for path, reason in [
        ("streamlit/dashboard.py", "dashboard KPI construction"),
        ("streamlit/app.py", "Streamlit layout and app entry point"),
        ("cortex-code-agent/policy.py", "configured agent and semantic scope"),
    ]:
        if (REPO_ROOT / path).exists():
            candidates.append(ProcessAsset(path=path, reason=reason))
    if any(t in lower for t in ("semantic", "metric", "revenue", "sales", "weather", "marketing")):
        sv_dir = REPO_ROOT / "semantic-views" / "definitions"
        if sv_dir.exists():
            candidates.append(ProcessAsset(path=str(sv_dir.relative_to(REPO_ROOT)), reason="semantic view YAML definitions"))
    return candidates[:6]


def discover_all(connection: str, *, database: str = SKI_RESORT_DATABASE, prompt: str = "") -> DiscoveryResult:
    return DiscoveryResult(
        agents=discover_agents(connection, database),
        semantic_views=discover_semantic_views(connection, database),
        tables=discover_tables(connection, database),
        process_docs=discover_process_context(prompt),
    )
