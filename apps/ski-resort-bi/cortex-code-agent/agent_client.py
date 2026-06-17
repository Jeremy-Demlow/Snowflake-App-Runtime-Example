"""Cortex Agents REST + SSE client.

Posts to ``/api/v2/databases/<db>/schemas/<sc>/agents/<n>:run`` with a
KEYPAIR_JWT bearer (minted from ``connections.toml``). Parses the SSE stream
and accumulates events into an :class:`AgentResponse` the Streamlit UI can
render natively.

Why REST instead of ``SNOWFLAKE.CORTEX.DATA_AGENT_RUN()`` SQL function:
- Streaming: live status / tool / SQL / table / text events as they happen.
- Time-to-first-byte ~1s vs ~25s for the synchronous SQL fn.
- Native thread continuity via ``thread_id`` + ``parent_message_id``.
- First-class citations and per-tool status frames.

CLI smoke test::

    SNOWFLAKE_CONNECTION_NAME=myconnection \\
        python3 cortex-code-agent/agent_client.py \\
        --agent SKI_RESORT_DEMO.AGENTS.RESORT_EXECUTIVE \\
        "What is total ticket revenue for the 2024-2025 season?"
"""
from __future__ import annotations

import json
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests

try:
    from ._jwt_auth import AgentSessionAuth, session_from_connection
except ImportError:  # standalone import
    from _jwt_auth import AgentSessionAuth, session_from_connection


# ---------- response dataclass -----------------------------------------------

@dataclass
class AgentResponse:
    """Structured result accumulated from one Cortex Agent run."""
    text: str = ""
    thinking: list[str] = field(default_factory=list)
    sql_queries: list[str] = field(default_factory=list)
    dataframes: list[pd.DataFrame] = field(default_factory=list)
    chart_specs: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    time_to_first_byte: float = 0.0
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0
    usage_cache_read: int = 0
    usage_cache_write: int = 0
    thread_id: str | None = None
    message_id: str | None = None
    raw_events: list[dict] = field(default_factory=list)

    def to_compact_payload(self, max_chars: int = 4000) -> str:
        parts: list[str] = []
        if self.text:
            parts.append(self.text)
        if self.tools_used:
            parts.append(f"\n[Agent used tools: {', '.join(self.tools_used)}]")
        if self.sql_queries:
            parts.append(f"[Agent ran {len(self.sql_queries)} SQL queries]")
        for i, df in enumerate(self.dataframes):
            if df.empty:
                continue
            head_csv = df.head(5).to_csv(index=False)
            parts.append(
                f"\n[Result table {i + 1}: {len(df)} rows x {len(df.columns)} cols]\n"
                f"{head_csv}"
            )
        if self.errors:
            parts.append("\n[Errors:]\n" + "\n".join(self.errors))
        out = "\n".join(p for p in parts if p)
        if len(out) > max_chars:
            out = out[: max_chars - 32] + "\n...[truncated for token budget]"
        return out


# ---------- helpers ---------------------------------------------------------

def _result_set_to_df(rs: dict) -> pd.DataFrame:
    data = rs.get("data", [])
    if not data:
        return pd.DataFrame()
    row_type = rs.get("resultSetMetaData", {}).get("rowType", [])
    if row_type:
        cols = [r.get("name", f"col_{i}") for i, r in enumerate(row_type)]
        if not isinstance(data[0], dict) and len(cols) != len(data[0]):
            warnings.warn("rowType / data column count mismatch; positional fallback")
            return pd.DataFrame(data)
        return pd.DataFrame(data, columns=cols)
    if isinstance(data[0], dict):
        return pd.DataFrame(data)
    return pd.DataFrame(data)


def _build_payload(
    prompt: str,
    history: list[dict] | None,
    thread_id: str | None,
    parent_message_id: str | None,
) -> dict:
    if thread_id:
        return {
            "messages": [{"role": "user",
                          "content": [{"type": "text", "text": prompt}]}],
            "thread_id": thread_id,
            "parent_message_id": parent_message_id or "0",
        }
    msgs: list[dict] = []
    for m in history or []:
        msgs.append({
            "role": m["role"],
            "content": [{"type": "text", "text": m["content"]}],
        })
    msgs.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
    return {"messages": msgs}


def _stream_sse(
    auth: AgentSessionAuth,
    database: str,
    schema: str,
    agent_name: str,
    payload: dict,
    timeout: int,
    agent_version: str | None = "DEFAULT",
):
    """Yield ``{event, data}`` dicts from the agent :run SSE endpoint."""
    endpoint = (
        f"{auth.host}/api/v2/databases/{database}"
        f"/schemas/{schema}/agents/{agent_name}:run"
    )
    with requests.post(
        endpoint,
        headers=auth.headers(accept="text/event-stream"),
        json=payload,
        params={"version": agent_version} if agent_version else None,
        stream=True,
        timeout=timeout,
    ) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"
        current_event: str | None = None
        data_buffer: list[str] = []
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            if not raw_line:
                if data_buffer and current_event is not None:
                    joined = "\n".join(data_buffer)
                    if joined == "[DONE]":
                        yield {"event": "done", "data": {}}
                        return
                    try:
                        yield {"event": current_event, "data": json.loads(joined)}
                    except json.JSONDecodeError as exc:
                        yield {
                            "event": "parse_error",
                            "data": {"raw_event": current_event, "error": str(exc)},
                        }
                current_event = None
                data_buffer = []
                continue
            if raw_line.startswith("event:"):
                current_event = raw_line[6:].strip()
            elif raw_line.startswith("data:"):
                data_buffer.append(raw_line[5:].strip())


def _accumulate(resp: AgentResponse, evt: str, data: dict, *, seen_tool_result: bool) -> bool:
    """Apply one parsed SSE frame to the response. Returns updated seen_tool_result."""
    if evt == "response.text.delta":
        text = data.get("text", "")
        if text:
            if seen_tool_result:
                resp.text += text
            else:
                # Pre-tool text — treat as thinking unless agent emits no tools
                if not resp.thinking:
                    resp.thinking.append(text)
                else:
                    resp.thinking[-1] += text

    elif evt == "response.thinking.delta":
        text = data.get("text") or data.get("thinking") or ""
        if text:
            if not resp.thinking:
                resp.thinking.append(text)
            else:
                resp.thinking[-1] += text

    elif evt == "response":
        text = data.get("thinking") or data.get("text", "")
        if text and not resp.text:
            resp.text = text

    elif evt == "response.status":
        msg = data.get("status_message") or data.get("message", "")
        if msg:
            resp.statuses.append(msg)

    elif evt == "response.tool_use":
        name = (data.get("name") or "").replace("cortex_analyst_text_to_sql__", "")
        if name and name not in resp.tools_used:
            resp.tools_used.append(name)

    elif evt == "response.tool_result":
        seen_tool_result = True
        for item in data.get("content", []):
            if not isinstance(item, dict):
                continue
            j = item.get("json", {})
            if not isinstance(j, dict):
                continue
            if j.get("sql"):
                resp.sql_queries.append(j["sql"])
            rs = j.get("result_set")
            if rs:
                resp.dataframes.append(_result_set_to_df(rs))
            err = j.get("error")
            if err:
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                resp.errors.append(msg)

    elif evt == "response.chart":
        spec_raw = data.get("chart_spec")
        if spec_raw:
            try:
                spec = json.loads(spec_raw) if isinstance(spec_raw, str) else spec_raw
                resp.chart_specs.append(spec)
            except (json.JSONDecodeError, TypeError):
                pass

    elif evt == "response.text.annotation":
        resp.citations.append(data)

    elif evt == "response.error":
        msg = data.get("message") or data.get("error", "An error occurred")
        resp.errors.append(msg)

    elif evt == "metadata":
        inner = data.get("metadata", data)
        tid = inner.get("thread_id")
        if tid is not None:
            resp.thread_id = str(tid)
        mid = inner.get("message_id") or inner.get("assistant_message_id")
        if mid is not None:
            resp.message_id = str(mid)
        usage_list = inner.get("usage", {}).get("tokens_consumed", [])
        for u in usage_list:
            inp = u.get("input_tokens", {})
            outp = u.get("output_tokens", {})
            resp.usage_input_tokens += int(inp.get("total", 0))
            resp.usage_cache_read += int(inp.get("cache_read", 0))
            resp.usage_cache_write += int(inp.get("cache_write", 0))
            resp.usage_output_tokens += int(outp.get("total", 0))

    elif evt == "parse_error":
        resp.errors.append(f"parse_error: {data}")

    return seen_tool_result


# ---------- public API -------------------------------------------------------

def call_cortex_agent(
    prompt: str,
    *,
    agent_fqn: str,
    connection: str,
    history: list[dict] | None = None,
    thread_id: str | None = None,
    parent_message_id: str | None = None,
    agent_version: str | None = "DEFAULT",
    on_event: Callable[[str, dict], None] | None = None,
    timeout: int = 120,
) -> AgentResponse:
    """Call a Cortex Agent over REST + SSE and return a populated AgentResponse.

    Args:
        prompt: User question.
        agent_fqn: ``DATABASE.SCHEMA.AGENT_NAME``.
        connection: Snowflake connection name (``connections.toml``); must use
            ``authenticator='SNOWFLAKE_JWT'`` with ``private_key_file``.
        history: Optional prior turns ``[{"role": ..., "content": ...}, ...]``.
        thread_id: Server-side thread id for multi-turn continuity.
        parent_message_id: Required when ``thread_id`` is set (else "0").
        on_event: Optional ``(event_name, data)`` callback for live UI hooks.
        timeout: HTTP timeout (seconds).
    """
    parts = agent_fqn.split(".")
    if len(parts) != 3:
        raise ValueError(f"agent_fqn must be DATABASE.SCHEMA.NAME, got {agent_fqn!r}")
    database, schema, name = parts

    auth = session_from_connection(connection)
    payload = _build_payload(prompt, history, thread_id, parent_message_id)

    resp = AgentResponse()
    t0 = time.monotonic()
    first_byte_t: float | None = None
    seen_tool_result = False
    try:
        for frame in _stream_sse(
            auth, database, schema, name, payload,
            timeout=timeout, agent_version=agent_version,
        ):
            if first_byte_t is None:
                first_byte_t = time.monotonic()
                resp.time_to_first_byte = round(first_byte_t - t0, 3)
            evt = frame.get("event", "")
            data = frame.get("data", {})
            resp.raw_events.append(frame)
            if on_event is not None:
                try:
                    on_event(evt, data)
                except Exception:
                    pass  # never let a UI callback abort the stream
            if evt == "done":
                break
            seen_tool_result = _accumulate(resp, evt, data, seen_tool_result=seen_tool_result)
    except requests.HTTPError as exc:
        body = ""
        if exc.response is not None:
            try:
                body = exc.response.text[:500]
            except Exception:
                body = ""
        resp.errors.append(f"HTTP {exc.response.status_code if exc.response else '?'}: {body}")
    except requests.RequestException as exc:
        resp.errors.append(f"Network error: {exc}")
    except Exception as exc:
        resp.errors.append(f"Unexpected error: {exc}")

    resp.duration_seconds = round(time.monotonic() - t0, 2)

    # If only thinking populated (tool-less run), promote to answer.
    if not resp.text and resp.thinking and not resp.errors:
        resp.text = "\n".join(resp.thinking)
    return resp


# ---------- CLI smoke test ---------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Smoke-test a Cortex Agent (REST+SSE).")
    parser.add_argument("prompt", help="Question to ask the agent")
    parser.add_argument(
        "--agent",
        default="SKI_RESORT_DEMO.AGENTS.RESORT_EXECUTIVE",
        help="DATABASE.SCHEMA.AGENT_NAME",
    )
    parser.add_argument(
        "--connection",
        default=os.environ.get("SNOWFLAKE_CONNECTION_NAME", "myconnection"),
    )
    parser.add_argument("--verbose", action="store_true", help="Print each SSE event")
    args = parser.parse_args(argv)

    print(f"Calling {args.agent} via {args.connection} (REST+SSE)...")

    def _printer(evt: str, data: dict) -> None:
        if args.verbose:
            preview = ""
            if evt == "response.text.delta":
                preview = repr(data.get("text", ""))[:60]
            elif evt == "response.tool_use":
                preview = f"name={data.get('name')}"
            elif evt == "response.status":
                preview = data.get("status_message") or data.get("message", "")
            print(f"  [{evt}] {preview}")

    resp = call_cortex_agent(
        args.prompt,
        agent_fqn=args.agent,
        connection=args.connection,
        on_event=_printer,
    )

    print(f"\n--- text ({len(resp.text)} chars) ---")
    print(resp.text or "(empty)")
    print(f"\n--- thinking blocks: {len(resp.thinking)}")
    print(f"--- tools_used: {resp.tools_used}")
    print(f"--- statuses: {resp.statuses}")
    print(f"--- sql queries: {len(resp.sql_queries)}")
    print(f"--- dataframes: {len(resp.dataframes)}")
    if resp.dataframes:
        df = resp.dataframes[0]
        print(f"\nFirst dataframe ({len(df)} x {len(df.columns)}):")
        print(df.head().to_string())
    print(f"\n--- usage: in={resp.usage_input_tokens} out={resp.usage_output_tokens} "
          f"cache_read={resp.usage_cache_read}")
    print(f"--- time_to_first_byte: {resp.time_to_first_byte}s")
    print(f"--- total: {resp.duration_seconds}s")
    print(f"--- thread_id: {resp.thread_id}")
    if resp.errors:
        print(f"--- ERRORS: {resp.errors}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
