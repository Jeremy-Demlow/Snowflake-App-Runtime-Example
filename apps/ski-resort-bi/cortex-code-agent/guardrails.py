"""PreToolUse guardrails for the governed SDK explorer.

These complement the read-only Snowflake role (the primary guardrail). They
give fast, explainable rejections before a query reaches Snowflake.
"""
from __future__ import annotations

import re
from collections.abc import Callable

try:
    from .policy import SCOPE_DATABASES
except ImportError:  # standalone import
    from policy import SCOPE_DATABASES


# Matches DATABASE.SCHEMA.OBJECT references so we can check the database part.
_FQN_RE = re.compile(r"\b([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)")
# Account-wide discovery that leaks other tenants' objects (e.g. SHOW AGENTS IN
# ACCOUNT surfaced unrelated SNOWFLAKE_INTELLIGENCE agents) and balloons context.
_ACCOUNT_WIDE_RE = re.compile(r"\bIN\s+ACCOUNT\b", re.IGNORECASE)
_SHOW_AGENTS_RE = re.compile(r"\bSHOW\s+AGENTS\b", re.IGNORECASE)


def scope_guard(
    allowed_databases: set[str] | None = None,
    tool_names: tuple[str, ...] = ("sql_execute", "SQL"),
) -> Callable:
    """PreToolUse factory: reject SQL outside the explorer's data scope.

    The read-only role already cannot access other databases; this hook makes
    the rejection fast and legible instead of a generic privilege error, and it
    also blocks account-wide discovery (SHOW AGENTS / IN ACCOUNT) that would
    leak unrelated tenants' objects and explode context.
    """
    allowed = {d.upper() for d in (allowed_databases or SCOPE_DATABASES)}

    def hook(inp, tool_use_id, ctx):
        if inp.get("tool_name") not in tool_names:
            return {"continue_": True}
        ti = inp.get("tool_input") or {}
        query = ti.get("query") or ti.get("sql") or ""

        # Block account-wide discovery before anything else.
        if _ACCOUNT_WIDE_RE.search(query) or _SHOW_AGENTS_RE.search(query):
            return {
                "continue_": False,
                "decision": "block",
                "reason": (
                    "Account-wide discovery (SHOW AGENTS / IN ACCOUNT) is not "
                    "allowed. Query the SKI_RESORT_DEMO marts/semantic views, or "
                    "call the deployed agent via DATA_AGENT_RUN."
                ),
            }

        referenced = {m.group(1).upper() for m in _FQN_RE.finditer(query)}
        out_of_scope = sorted(db for db in referenced if db not in allowed)
        if out_of_scope:
            return {
                "continue_": False,
                "decision": "block",
                "reason": (
                    f"Out-of-scope database(s): {', '.join(out_of_scope)}. "
                    f"This explorer is limited to {', '.join(sorted(allowed))}."
                ),
            }
        return {"continue_": True}

    return hook
