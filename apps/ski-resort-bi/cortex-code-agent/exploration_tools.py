"""Due-diligence exploration tools used by cocosdkagent alongside the
Cortex Agent call. These let the model surface adjacent context the agent
didn't volunteer, so the assistant can say "I also went and looked at X".

Each tool returns a small text payload (well under the model's per-call budget).
"""
from __future__ import annotations

import snowflake.connector

try:
    from .policy import SKI_RESORT_DATABASE, SKI_RESORT_SEMANTIC_SCHEMA
except ImportError:  # standalone import
    from policy import SKI_RESORT_DATABASE, SKI_RESORT_SEMANTIC_SCHEMA


def list_semantic_views(database: str = SKI_RESORT_DATABASE) -> str:
    """List semantic views available for additional context.

    Args:
        database: Snowflake database to scan. Defaults to the ski-resort DB.

    Returns:
        Bulleted text list of ``schema.view`` plus comment, or an error message.
    """
    conn = snowflake.connector.connect(connection_name=_active_connection())
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW SEMANTIC VIEWS IN DATABASE {database}")
            rows = cur.fetchall()
            cols = [c[0].lower() for c in cur.description]
    finally:
        conn.close()

    if not rows:
        return f"No semantic views found in {database}."

    name_idx = cols.index("name")
    schema_idx = cols.index("schema_name")
    comment_idx = cols.index("comment") if "comment" in cols else None

    lines = [f"Semantic views in {database}:"]
    for r in rows:
        comment = r[comment_idx] if comment_idx is not None and r[comment_idx] else ""
        comment_str = f" - {comment}" if comment else ""
        lines.append(f"  - {r[schema_idx]}.{r[name_idx]}{comment_str}")
    return "\n".join(lines)


def describe_semantic_view(fqn: str) -> str:
    """Describe a semantic view's tables, dimensions, and metrics.

    Args:
        fqn: Fully qualified ``DATABASE.SCHEMA.VIEW_NAME``.

    Returns:
        Compact summary of metrics + dimensions + tables, capped at ~3 KB.
    """
    parts = fqn.split(".")
    if len(parts) != 3:
        return f"Error: fqn must be DATABASE.SCHEMA.VIEW_NAME, got {fqn!r}"

    conn = snowflake.connector.connect(connection_name=_active_connection())
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(f"DESCRIBE SEMANTIC VIEW {fqn}")
            except snowflake.connector.errors.ProgrammingError as exc:
                return f"Error describing {fqn}: {exc}"
            rows = cur.fetchall()
            cols = [c[0].lower() for c in cur.description]
    finally:
        conn.close()

    if not rows:
        return f"No description rows for {fqn}."

    object_kind_idx = cols.index("object_kind") if "object_kind" in cols else None
    name_idx = cols.index("object_name") if "object_name" in cols else cols.index("name")
    comment_idx = cols.index("comment") if "comment" in cols else None

    metrics: list[str] = []
    dimensions: list[str] = []
    tables: list[str] = []
    seen: set[tuple[str, str]] = set()
    for r in rows:
        kind = (r[object_kind_idx] or "").upper() if object_kind_idx is not None else ""
        name = r[name_idx]
        if (kind, name) in seen:
            continue
        seen.add((kind, name))
        comment = r[comment_idx] if comment_idx is not None and r[comment_idx] else ""
        suffix = f" - {comment}" if comment else ""
        line = f"  - {name}{suffix}"
        if kind == "METRIC":
            metrics.append(line)
        elif kind == "DIMENSION":
            dimensions.append(line)
        elif kind == "TABLE":
            tables.append(line)

    out: list[str] = [f"Semantic view: {fqn}"]
    if tables:
        out.append("\nTables:")
        out.extend(tables[:20])
    if metrics:
        out.append("\nMetrics:")
        out.extend(metrics[:30])
    if dimensions:
        out.append("\nDimensions:")
        out.extend(dimensions[:30])
    body = "\n".join(out)
    if len(body) > 3000:
        body = body[:3000] + "\n...[truncated]"
    return body


# ---------- helpers ----------------------------------------------------------

def _active_connection() -> str:
    """Connection name used by exploration queries.

    Reads ``SNOWFLAKE_CONNECTION_NAME`` env var; defaults to ``myconnection``.
    """
    import os
    return os.environ.get("SNOWFLAKE_CONNECTION_NAME", "myconnection")
