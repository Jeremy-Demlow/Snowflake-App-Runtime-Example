"""Persistent BI chat panel.

Primary path: the Cortex Code SDK governed explorer (bridge.AgentSession) runs
its own sql_execute loop under read-only guardrails, optionally calling the
deployed agent / semantic views. Each tool call is captured as an evidence item
for the Trace tab.

Optional fast path: the deterministic broker (semantic_broker.run_semantic_turn)
can short-circuit canned dashboard questions when enabled in settings.
"""
from __future__ import annotations

import json
import time
from typing import Any

import pandas as pd
import streamlit as st

# Caps so a chatty result set can't blow up the message or render junk charts.
_TABLE_ROW_CAP = 1000
_CHART_ROW_CAP = 100
_MAX_TABLES_PER_MSG = 3

from bridge import get_or_create_session
from cortex_code_agent import BIAnswer, CORTEX_AGENTS, EXPLORER_CONNECTION, call_cortex_agent
from settings_panel import render_settings_panel

SUGGESTIONS: dict[str, str] = {
    "Revenue uptick": "What's causing the uptick in revenue these last couple of days?",
    "F&B vs tickets": "How much of total revenue comes from food and beverage vs ticket sales recently?",
    "Rental trend": "Are equipment rentals trending up or down versus ticket sales recently?",
}

# Map a streamed tool name to an evidence-provider label for the trace.
_PROVIDER_BY_TOOL = {
    "sql_execute": "sql",
    "SQL": "sql",
    "Read": "process",
    "Glob": "process",
    "Grep": "process",
}


def _provider_for(tool_name: str, summary: str) -> str:
    """Classify a tool call for the Trace. A sql_execute that calls
    DATA_AGENT_RUN is consulting the deployed agent, so label it `agent`."""
    if tool_name in ("sql_execute", "SQL") and "DATA_AGENT_RUN" in (summary or "").upper():
        return "agent"
    return _PROVIDER_BY_TOOL.get(tool_name, "other")


def _tool_result_to_df(raw: str) -> pd.DataFrame | None:
    """Parse an explorer sql_execute result (a JSON string from sql_format=json)
    into a DataFrame. Returns None on any parse failure or an empty result set.

    Accepts either a bare ``[{...}, ...]`` array of row dicts or a
    ``{"data": [...]}`` envelope. Defensive by design — a bad frame must never
    break the chat message."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if isinstance(parsed, dict):
        parsed = parsed.get("data") or parsed.get("rows") or parsed.get("result")
    if not isinstance(parsed, list) or not parsed:
        return None
    try:
        df = pd.DataFrame(parsed)
    except (ValueError, TypeError):
        return None
    if df.empty:
        return None
    # The explorer's json sql_format encodes every cell as a JSON scalar string:
    # dates arrive double-quoted ('"2026-12-18"') and numbers as quoted strings
    # ('8719'). Decode each cell back to its real scalar so numbers are numeric
    # and dates are clean (fixes both auto-charting and the table display).
    def _decode(v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return v
        return v

    # Apply unconditionally: _decode is a no-op for non-strings, and gating on
    # ``dtype == object`` misses string-typed columns on pandas builds that infer
    # a dedicated string dtype.
    for col in df.columns:
        df[col] = df[col].map(_decode)
    df = df.infer_objects()
    if len(df) > _TABLE_ROW_CAP:
        df = df.head(_TABLE_ROW_CAP)
    return df


def _auto_chart(df: pd.DataFrame, container: Any) -> None:
    """Render a conservative auto-chart beneath a result table.

    Picks an x-axis and numeric series from a small result (2-100 rows):
      - Prefer the first datetime-parseable column as x -> line chart (other
        descriptive dimension columns are ignored, so a typical
        date + season + flag + metric result still charts).
      - Else, if there is exactly one non-numeric column, use it as a
        categorical x -> bar chart.
      - Else render nothing (the table already shows).
    Boolean flag columns are excluded from the numeric y-series. Wrapped so a
    weird frame never breaks the message."""
    try:
        if not isinstance(df, pd.DataFrame) or not (2 <= len(df) <= _CHART_ROW_CAP):
            return

        def _is_numeric(col: str) -> bool:
            return (
                pd.api.types.is_numeric_dtype(df[col])
                and not pd.api.types.is_bool_dtype(df[col])
            )

        numeric_cols = [c for c in df.columns if _is_numeric(c)]
        if not numeric_cols:
            return
        non_numeric = [c for c in df.columns if c not in numeric_cols]

        x_col: str | None = None
        is_dt = False
        for c in non_numeric:
            if pd.to_datetime(df[c], errors="coerce").notna().all():
                x_col, is_dt = c, True
                break
        if x_col is None:
            if len(non_numeric) == 1:
                x_col = non_numeric[0]
            else:
                return  # ambiguous x -> table only

        y_cols = [c for c in numeric_cols if c != x_col]
        if not y_cols:
            return
        plot = df[[x_col, *y_cols]].set_index(x_col)
        if is_dt:
            container.line_chart(plot, use_container_width=True)
        else:
            container.bar_chart(plot, use_container_width=True)
    except Exception:  # noqa: BLE001 - charts are best-effort
        return



def _init_state() -> None:
    st.session_state.setdefault("bi_messages", [])
    st.session_state.setdefault("bi_last_evidence", [])
    st.session_state.setdefault("bi_last_usage", {})
    st.session_state.setdefault("bi_pending_prompt", None)
    st.session_state.setdefault("coco_settings", {})
    # Agent multi-turn memory: prior user/assistant turns sent to the deployed
    # agent (the REST :run is stateless / returns no thread_id, so we carry
    # history ourselves). Capped to the most recent turns.
    st.session_state.setdefault("agent_history", [])

_AGENT_HISTORY_MAX_MSGS = 12  # ~6 turns of (user, assistant)


def _tool_input_summary(tool_name: str, tool_input: dict) -> str:
    if tool_name in ("sql_execute", "SQL"):
        return tool_input.get("query") or tool_input.get("sql") or ""
    return ", ".join(f"{k}={v}" for k, v in (tool_input or {}).items())


def _render_evidence_expander(evidence: list[dict]) -> None:
    if not evidence:
        return
    ok = sum(1 for e in evidence if not e.get("error"))
    with st.expander(f"Evidence checked ({ok}/{len(evidence)} succeeded)", expanded=False):
        for e in evidence:
            status = "error" if e.get("error") else "ok"
            st.markdown(f"- `{e['provider']}` · `{e.get('tool', '')}`: **{status}**")


def _render_explore_message(msg: dict) -> None:
    # In agent-aware mode, show the agent's answer prominently first.
    agent_evidence = [e for e in msg.get("evidence", []) if e.get("provider") == "agent"]
    if agent_evidence:
        agent_text = agent_evidence[0].get("result_preview", "")
        if agent_text:
            st.markdown("**Resort Executive Agent:**")
            st.markdown(agent_text)
            st.divider()

    explorer_text = msg.get("text") or ""
    if explorer_text:
        if agent_evidence:
            st.markdown("**Explorer enhancement:**")
        st.markdown(explorer_text)
    elif not agent_evidence:
        st.markdown("_(no answer text)_")

    show_charts = bool((st.session_state.get("coco_settings", {}) or {}).get("show_charts", True))

    # Agent-authored Vega-Lite charts first (richest signal).
    if show_charts:
        for spec in msg.get("charts", []) or []:
            try:
                st.vega_lite_chart(spec, use_container_width=True)
            except Exception:  # noqa: BLE001 - a bad spec must not break the turn
                pass

    for df in msg.get("tables", [])[:_MAX_TABLES_PER_MSG]:
        if isinstance(df, pd.DataFrame) and not df.empty:
            st.dataframe(df, hide_index=True, use_container_width=True)
            if show_charts:
                _auto_chart(df, st)
    _render_evidence_expander(msg.get("evidence", []))
    u = msg.get("usage") or {}
    mode_label = "Agent-aware" if msg.get("prompt_mode") == "agent" else "Explore-only"
    consulted = any(e.get("provider") == "agent" for e in msg.get("evidence", []))
    badge = f"{mode_label}" + (" · consulted agent" if consulted else "")
    if u:
        st.caption(
            f"[{badge}] in {u.get('input_tokens', 0):,} · out {u.get('output_tokens', 0):,} "
            f"· {u.get('elapsed_s', 0)}s · turns {u.get('tool_calls', 0)}"
        )


def _prefetch_agent(prompt: str, status) -> dict | None:
    """Agent-aware mode: consult the deployed agent via REST before the SDK turn.

    Returns an evidence dict (provider 'agent') with the agent's text, or None on
    failure. Uses the REST client (no ~10s sql_execute cap), streaming status.
    """
    spec = CORTEX_AGENTS.get("resort_executive", {})
    fqn = spec.get("fqn", "SKI_RESORT_DEMO.AGENTS.RESORT_EXECUTIVE")
    status.update(label="Consulting the RESORT_EXECUTIVE agent...", state="running")
    slot = st.empty()

    def _on_event(event: str, data: dict) -> None:
        if event == "response.status":
            msg = data.get("status_message") or data.get("message", "")
            if msg:
                slot.caption(f"Agent: {msg}")

    t0 = time.monotonic()
    history = list(st.session_state.get("agent_history", []))
    try:
        resp = call_cortex_agent(
            prompt, agent_fqn=fqn, connection=EXPLORER_CONNECTION,
            history=history, on_event=_on_event, timeout=180,
        )
    except Exception as exc:  # noqa: BLE001
        slot.warning(f"Agent consult failed ({exc}); exploring directly.")
        return None
    answer = (resp.text or "").strip()
    elapsed = round(time.monotonic() - t0, 1)
    if not answer:
        slot.caption(f"Agent returned no text in {elapsed}s; exploring directly.")
        return None
    # Persist this turn so the agent remembers it next time (history-based memory).
    hist = st.session_state.get("agent_history", [])
    hist.append({"role": "user", "content": prompt})
    hist.append({"role": "assistant", "content": answer})
    st.session_state["agent_history"] = hist[-_AGENT_HISTORY_MAX_MSGS:]
    slot.caption(f"Agent answered in {elapsed}s; the explorer will enhance it.")
    return {
        "provider": "agent",
        "tool": "RESORT_EXECUTIVE",
        "input": prompt,
        "error": "",
        "result_preview": answer[:1500],
        # Rich payload (popped by _run_explorer_turn before the evidence is
        # rendered): the agent's own result tables + Vega-Lite chart specs.
        "dataframes": [df for df in resp.dataframes if isinstance(df, pd.DataFrame) and not df.empty],
        "chart_specs": list(resp.chart_specs or []),
    }


def _run_explorer_turn(prompt: str) -> dict:
    """Drive the SDK governed explorer and capture evidence + answer.

    In agent-aware mode, the deployed agent is consulted first (REST pre-fetch)
    and its answer is injected into the explorer prompt for verification.
    """
    session = get_or_create_session(st.session_state, st.session_state.get("coco_conn", ""))
    prompt_mode = (st.session_state.get("coco_settings", {}) or {}).get("prompt_mode", "explore")

    text_parts: list[str] = []
    evidence: list[dict] = []
    tables: list[pd.DataFrame] = []
    charts: list[dict] = []
    pending: dict[str, dict] = {}
    t0 = time.monotonic()

    status = st.status("Working...", expanded=True, state="running")
    with status:
        explorer_prompt = prompt
        if prompt_mode == "agent":
            agent_ev = _prefetch_agent(prompt, status)
            if agent_ev:
                # Pop the rich payload so the rendered evidence stays lean; the
                # agent's own tables + Vega charts go straight onto the message.
                charts.extend(agent_ev.pop("chart_specs", []) or [])
                tables.extend(agent_ev.pop("dataframes", []) or [])
                evidence.append(agent_ev)
                explorer_prompt = (
                    f"{prompt}\n\n[RESORT_EXECUTIVE agent answer]\n"
                    f"{agent_ev['result_preview']}\n[end agent answer]\n\n"
                    "The agent's answer is the trusted baseline. Enhance it with "
                    "a deeper breakdown (channel, location, trend, segment) the "
                    "user would find useful."
                )
        status.update(label="Exploring the data...", state="running")
        text_ph = st.empty()
        for ev in session.send_events(explorer_prompt):
            kind = ev.get("kind")
            if kind == "text":
                text_parts.append(ev.get("delta", ""))
                text_ph.markdown("".join(text_parts))
            elif kind == "tool_use":
                tool = ev.get("tool_name", "?")
                summary = _tool_input_summary(tool, ev.get("tool_input", {}))
                provider = _provider_for(tool, summary)
                pending[ev.get("tool_use_id", "")] = {
                    "provider": provider,
                    "tool": tool,
                    "input": summary,
                }
                status.update(label=f"Running {tool}...", state="running")
                if provider == "sql" and summary:
                    st.code(summary, language="sql")
                else:
                    st.write(f"Calling `{tool}`")
            elif kind == "tool_result":
                rec = pending.pop(ev.get("tool_use_id", ""), {"provider": "other", "tool": "?", "input": ""})
                is_err = bool(ev.get("is_error"))
                rec["error"] = ev.get("tool_result", "")[:400] if is_err else ""
                rec["result_preview"] = "" if is_err else str(ev.get("tool_result", ""))[:1500]
                evidence.append(rec)
                # Parse a successful SQL result into a table for rich display.
                if not is_err and rec.get("provider") == "sql" and len(tables) < _MAX_TABLES_PER_MSG:
                    df = _tool_result_to_df(ev.get("tool_result", ""))
                    if df is not None:
                        tables.append(df)
                if is_err:
                    st.warning(f"{rec['tool']} hit an issue; the explorer will adapt.")
            elif kind == "error":
                st.error(ev.get("message", "Explorer error."))
            elif kind == "done":
                break
        elapsed = time.monotonic() - t0
        status.update(label=f"Done · {elapsed:.1f}s", state="complete", expanded=False)

    use = session.usage
    usage = {
        "input_tokens": getattr(use, "input_tokens", 0),
        "output_tokens": getattr(use, "output_tokens", 0),
        "tool_calls": len(evidence),
        "elapsed_s": round(time.monotonic() - t0, 1),
    }
    return {
        "role": "assistant",
        "mode": "explore",
        "prompt_mode": prompt_mode,
        "text": "".join(text_parts).strip(),
        "evidence": evidence,
        "tables": tables[:_MAX_TABLES_PER_MSG],
        "charts": charts,
        "usage": usage,
    }


def _render_chat() -> None:
    for msg in st.session_state["bi_messages"]:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                if msg.get("mode") == "fast" and isinstance(msg.get("answer"), BIAnswer):
                    _render_fast_answer(msg["answer"])
                else:
                    _render_explore_message(msg)
            else:
                st.markdown(msg.get("text", ""))

    if not st.session_state["bi_messages"]:
        pick = st.pills("Try asking", list(SUGGESTIONS), label_visibility="collapsed")
        if pick:
            st.session_state["bi_pending_prompt"] = SUGGESTIONS[pick]

    typed = st.chat_input("Ask about this dashboard...")
    prompt = st.session_state.pop("bi_pending_prompt", None) or typed
    if not prompt:
        return

    st.session_state["bi_messages"].append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    settings = st.session_state.get("coco_settings", {}) or {}
    use_fast_path = bool(settings.get("fast_path", False))

    with st.chat_message("assistant"):
        if use_fast_path:
            answer = _run_fast_path(prompt, settings)
            _render_fast_answer(answer)
            st.session_state["bi_messages"].append(
                {"role": "assistant", "mode": "fast", "answer": answer}
            )
        else:
            msg = _run_explorer_turn(prompt)
            _render_explore_message(msg)
            st.session_state["bi_last_evidence"] = msg["evidence"]
            st.session_state["bi_last_usage"] = msg["usage"]
            st.session_state["bi_messages"].append(msg)
    # Rerun only the chat fragment (not the whole page) so the dashboard stays
    # put and the conversation re-renders cleanly from session_state.
    st.rerun(scope="fragment")


# --- optional deterministic fast path ----------------------------------------

def _run_fast_path(prompt: str, settings: dict) -> BIAnswer:
    from cortex_code_agent import run_semantic_turn
    s = dict(settings)
    s.setdefault("due_diligence", "shallow")
    s.setdefault("max_evidence_steps", 5)
    return run_semantic_turn(prompt, connection=st.session_state.get("coco_conn", "myconnection"), settings=s)


def _render_fast_answer(answer: BIAnswer) -> None:
    st.markdown(answer.text)
    show_charts = bool((st.session_state.get("coco_settings", {}) or {}).get("show_charts", True))
    for df in answer.tables[:3]:
        if isinstance(df, pd.DataFrame) and not df.empty:
            st.dataframe(df, hide_index=True, use_container_width=True)
            if show_charts:
                _auto_chart(df, st)
    if answer.evidence:
        ok = sum(1 for ev in answer.evidence if not ev.errors)
        with st.expander(f"Evidence checked ({ok}/{len(answer.evidence)} succeeded)", expanded=False):
            for ev in answer.evidence:
                status = "error" if ev.errors else "ok"
                st.markdown(f"- `{ev.provider}` on `{ev.target}`: **{status}** — {ev.purpose}")
    st.caption(f"[fast path] route: {answer.route_summary or 'none'} · confidence: {answer.confidence}")


# --- trace + debug -----------------------------------------------------------

def _render_trace() -> None:
    evidence = st.session_state.get("bi_last_evidence", [])
    if not evidence:
        st.caption("No evidence trace yet. Ask a question in the Chat tab.")
        return
    usage = st.session_state.get("bi_last_usage", {})
    if usage:
        st.markdown(
            f"**Usage:** in {usage.get('input_tokens', 0):,} · "
            f"out {usage.get('output_tokens', 0):,} · "
            f"{usage.get('tool_calls', 0)} tool calls · {usage.get('elapsed_s', 0)}s"
        )
    for idx, e in enumerate(evidence, start=1):
        icon = ":material/error:" if e.get("error") else ":material/check_circle:"
        with st.expander(f"{icon} {idx}. {e['provider']} · {e.get('tool', '')}", expanded=idx == 1):
            if e.get("input"):
                lang = "sql" if e["provider"] == "sql" else "text"
                st.code(e["input"], language=lang)
            if e.get("error"):
                st.error(e["error"])
            elif e.get("result_preview"):
                st.text(e["result_preview"])


def _render_debug() -> None:
    st.markdown("**Session state**")
    st.json({
        "messages": len(st.session_state.get("bi_messages", [])),
        "evidence_items": len(st.session_state.get("bi_last_evidence", [])),
        "settings": st.session_state.get("coco_settings", {}),
    })
    stderr = st.session_state.get("coco_stderr", [])
    if stderr:
        st.markdown("**Explorer stderr (recent)**")
        st.code("\n".join(stderr[-40:]), language="text")
    if st.button("Clear BI chat", use_container_width=True):
        st.session_state["bi_messages"] = []
        st.session_state["bi_last_evidence"] = []
        st.session_state["bi_last_usage"] = {}
        st.session_state["agent_history"] = []
        st.rerun(scope="fragment")


def render_chat_panel(connection: str) -> None:
    _init_state()
    tabs = st.tabs(["Chat", "Settings", "Trace", "Debug"])
    with tabs[0]:
        _render_chat()
    with tabs[1]:
        render_settings_panel()
    with tabs[2]:
        _render_trace()
    with tabs[3]:
        _render_debug()
