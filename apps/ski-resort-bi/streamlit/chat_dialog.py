"""Native st.dialog chat surface for the Cortex Code Agent (REQ-014).

Renders inline tool-use cards as the agent fires tools, auto-renders SQL
results as st.dataframe, streams text token-by-token, and exposes audit +
stderr in a Debug expander.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import streamlit as st

from cocosdkagent import ToolResult
from cocosdkagent.streamlit import render_tool_result

from bridge import AgentSession, get_or_create_session

SUGGESTIONS: dict[str, str] = {
    ":blue[:material/insights:] Revenue vs visitation": (
        "Is my revenue trend correlated with lift-scan visitation over the last "
        "30 days of data? Use SKI_RESORT_DEMO.MARTS.FACT_TICKET_SALES "
        "(purchase_date, purchase_amount) and "
        "SKI_RESORT_DEMO.MARTS.FACT_LIFT_SCANS (scan_timestamp). "
        "Anchor the window on MAX(purchase_date)."
    ),
    ":green[:material/restaurant:] Food orders impact": (
        "How much of total revenue comes from food and beverage vs ticket "
        "sales for the last 30 days of available data? Compare "
        "SKI_RESORT_DEMO.MARTS.FACT_FOOD_BEVERAGE to "
        "SKI_RESORT_DEMO.MARTS.FACT_TICKET_SALES."
    ),
    ":violet[:material/snowboarding:] Equipment rentals": (
        "Are equipment rentals trending up or down vs ticket sales over "
        "the last 30 days of data? Use SKI_RESORT_DEMO.MARTS.FACT_RENTALS "
        "and SKI_RESORT_DEMO.MARTS.FACT_TICKET_SALES."
    ),
}

TOOL_ICON = {
    "SQL": ":material/database:",
    "sql_execute": ":material/database:",
    "Read": ":material/description:",
    "Glob": ":material/search:",
    "Grep": ":material/manage_search:",
    "call_resort_executive": ":material/smart_toy:",
    "call_ski_ops_assistant": ":material/smart_toy:",
    "list_resort_semantic_views": ":material/list:",
    "describe_resort_semantic_view": ":material/description:",
}

SQL_TOOLS = {"SQL", "sql_execute"}
AGENT_TOOLS = {"call_resort_executive", "call_ski_ops_assistant"}
EXPLORATION_TOOLS = {"list_resort_semantic_views", "describe_resort_semantic_view"}

_RESP_ID_RE = re.compile(r"\[response_id:\s*([\w_]+)\]")


def _init_state() -> None:
    st.session_state.setdefault("coco_messages", [])
    st.session_state.setdefault("coco_audit", [])
    st.session_state.setdefault("coco_stderr", [])
    st.session_state.setdefault("coco_pending_prompt", None)


def _status_strip(session: AgentSession) -> None:
    if session._chat is not None:
        from cocosdkagent.streamlit import render_status_strip, auto_refresh
        from cortex_code_agent import DEFAULT_MAX_TURNS
        if st.session_state.get("coco_in_flight"):
            auto_refresh(session._chat, render_status_strip, interval=1.0,
                         key="coco_live_strip")
        else:
            render_status_strip(session._chat, extra={
                "max_turns": str(DEFAULT_MAX_TURNS),
            })
    else:
        st.caption("Connecting…")


def _render_history(session: AgentSession | None = None) -> None:
    """Static (non-spinning) re-render of past turns.

    Live spinners are only used during an in-flight turn (`_drain_and_render`);
    when the dialog is closed and reopened, every historical message is inert.
    """
    for msg in st.session_state["coco_messages"]:
        with st.chat_message(msg["role"]):
            for part in msg.get("parts", []):
                if part.get("type") == "text":
                    st.markdown(part.get("text", ""))
                elif part.get("type") == "tool":
                    _render_static_tool(part, session=session)


def _render_static_tool(tool: dict[str, Any], session: AgentSession | None = None) -> None:
    """History-mode tool card: collapsed expander, no spinner."""
    icon = TOOL_ICON.get(tool.get("tool", ""), ":material/build:")
    name = tool.get("tool", "?")
    dur = tool.get("duration")
    suffix = f" · {dur:.1f}s" if isinstance(dur, (int, float)) else ""
    if tool.get("is_error"):
        suffix += " · failed"
    with st.expander(f"{icon} {name}{suffix}", expanded=False):
        try:
            st.code(json.dumps(tool.get("input", {}), indent=2, default=str), language="json")
        except Exception:
            st.write(tool.get("input"))
        _render_tool_payload(tool, session=session)


def _render_agent_response(session: AgentSession, response_id: str) -> None:
    """Render a stashed AgentResponse natively: text, dataframes, charts."""
    resp = session.agent_responses.get(response_id)
    if resp is None:
        return
    if resp.text:
        st.markdown(resp.text)
    for i, df in enumerate(resp.dataframes):
        if df is None or df.empty:
            continue
        st.dataframe(df, hide_index=True, use_container_width=True)
    for spec in resp.chart_specs:
        try:
            st.vega_lite_chart(spec, use_container_width=True)
        except Exception:
            st.json(spec)
    if resp.sql_queries:
        with st.expander(f"SQL ({len(resp.sql_queries)})", expanded=False):
            for q in resp.sql_queries:
                st.code(q, language="sql")
    if resp.suggested_queries:
        with st.expander("Suggested follow-ups", expanded=False):
            for q in resp.suggested_queries:
                st.markdown(f"- {q}")
    if resp.errors:
        st.warning("Agent reported errors: " + " | ".join(resp.errors))


def _render_tool_payload(tool: dict[str, Any], session: AgentSession | None = None) -> None:
    """Render the result body of a tool call.

    For our agent-call tools, the result text contains a ``[response_id: ...]``
    marker; we look up the stashed AgentResponse and render dataframes/charts
    natively instead of dumping the compact payload.
    """
    if tool.get("is_error"):
        st.error(f"Tool `{tool.get('tool')}` failed: {str(tool.get('result', ''))[:500]}")
        return
    raw = tool.get("result", "")
    if not raw or not str(raw).strip():
        return

    tool_name = tool.get("tool", "")

    # Agent calls: render the AgentResponse natively.
    if tool_name in AGENT_TOOLS and session is not None:
        m = _RESP_ID_RE.search(str(raw))
        if m:
            _render_agent_response(session, m.group(1))
            return

    tr = ToolResult(raw, tool_name=tool_name)
    if tr.metadata["is_describe"] and tool_name in SQL_TOOLS:
        try:
            df = tr.as_dataframe()
            if len(df.columns) > 5:
                keep = [c for c in df.columns
                        if c.lower() in {"name", "type", "null?", "comment"}]
                if keep:
                    st.dataframe(df[keep], hide_index=True)
                    return
        except Exception:
            pass
    render_tool_result(tr)





def _render_pills(session: AgentSession) -> None:
    if st.session_state["coco_messages"]:
        return
    st.caption("Try asking:")
    pick = st.pills(
        "suggestions",
        list(SUGGESTIONS.keys()),
        label_visibility="collapsed",
        key="coco_pills",
    )
    if pick:
        st.session_state["coco_pending_prompt"] = SUGGESTIONS[pick]


def _drain_and_render(prompt: str, session: AgentSession) -> None:
    """Live-render an in-flight agent turn with a top-level st.status,
    per-tool sub-statuses (running -> complete/error with elapsed), and
    1Hz heartbeat-driven elapsed counter so the user never sees a frozen UI.
    """
    msgs = st.session_state["coco_messages"]
    msgs.append({"role": "user", "parts": [{"type": "text", "text": prompt}]})
    with st.chat_message("user"):
        st.markdown(prompt)

    assistant: dict[str, Any] = {"role": "assistant", "parts": []}
    t0 = time.monotonic()

    with st.chat_message("assistant"):
        status = st.status("Cortex Code is thinking\u2026 0s", expanded=True, state="running")
        with status:
            text_buf: list[str] = []
            text_ph = st.empty()
            live: dict[str, dict[str, Any]] = {}
            phase = "thinking"
            had_error = False

            for ev in session.send_events(prompt):
                elapsed = time.monotonic() - t0
                kind = ev.get("kind")

                if kind == "heartbeat":
                    label_map = {
                        "thinking": "Cortex Code is thinking…",
                        "tool": "Calling tool…",
                        "text": "Generating answer…",
                    }
                    base = label_map.get(phase, "Working…")
                    status.update(label=f"{base} {elapsed:.0f}s")

                elif kind == "text":
                    phase = "text"
                    text_buf.append(ev.get("delta", ""))
                    text_ph.markdown("".join(text_buf))
                    status.update(label=f"Generating answer\u2026 {elapsed:.0f}s")

                elif kind == "tool_use":
                    phase = "tool"
                    if text_buf:
                        assistant["parts"].append({"type": "text", "text": "".join(text_buf)})
                        text_buf = []
                    tool_name = ev.get("tool_name", "?")
                    tool_id = ev.get("tool_use_id", "") or f"tool_{len(live)}"
                    icon = TOOL_ICON.get(tool_name, ":material/build:")
                    sub = st.status(f"{icon} {tool_name} \u00b7 running", expanded=False, state="running")
                    with sub:
                        try:
                            st.code(
                                json.dumps(ev.get("tool_input", {}) or {}, indent=2, default=str),
                                language="json",
                            )
                        except Exception:
                            st.write(ev.get("tool_input"))
                    live[tool_id] = {
                        "sub": sub,
                        "t_start": time.monotonic(),
                        "tool": tool_name,
                        "input": ev.get("tool_input", {}) or {},
                        "id": tool_id,
                    }
                    status.update(label=f"Calling {tool_name}\u2026 {elapsed:.0f}s")
                    text_ph = st.empty()

                elif kind == "tool_result":
                    tid = ev.get("tool_use_id", "")
                    rec = live.get(tid)
                    if rec is None:
                        rec = live.get(next(iter(live), ""), None)
                    is_err = bool(ev.get("is_error"))
                    raw = ev.get("tool_result", "")
                    if rec is not None:
                        dur = time.monotonic() - rec["t_start"]
                        icon = TOOL_ICON.get(rec["tool"], ":material/build:")
                        new_state = "error" if is_err else "complete"
                        suffix = "failed" if is_err else f"{dur:.1f}s"
                        rec["sub"].update(
                            label=f"{icon} {rec['tool']} \u00b7 {suffix}",
                            state=new_state,
                            expanded=is_err or rec["tool"] in SQL_TOOLS,
                        )
                        with rec["sub"]:
                            tool_part = {
                                "type": "tool",
                                "tool": rec["tool"],
                                "input": rec["input"],
                                "id": rec["id"],
                                "result": raw,
                                "is_error": is_err,
                                "duration": dur,
                            }
                            _render_tool_payload(tool_part, session=session)
                            assistant["parts"].append(tool_part)
                    else:
                        tool_part = {
                            "type": "tool",
                            "tool": "?",
                            "input": {},
                            "id": tid,
                            "result": raw,
                            "is_error": is_err,
                        }
                        _render_tool_payload(tool_part, session=session)
                        assistant["parts"].append(tool_part)
                    text_ph = st.empty()

                elif kind == "error":
                    had_error = True
                    msg = ev.get("message", "Unknown error.")
                    st.error(msg)
                    assistant["parts"].append({"type": "text", "text": f"_Error: {msg}_"})

                elif kind == "done":
                    if text_buf:
                        assistant["parts"].append({"type": "text", "text": "".join(text_buf)})
                    final_state = "error" if had_error else "complete"
                    final_label = (
                        f"Failed after {elapsed:.1f}s" if had_error else f"Done \u00b7 {elapsed:.1f}s"
                    )
                    status.update(label=final_label, state=final_state, expanded=True)
                    break

    msgs.append(assistant)


def _render_debug(session: AgentSession) -> None:
    audit = st.session_state["coco_audit"]
    stderr = st.session_state["coco_stderr"]
    with st.expander(f"Debug · audit ({len(audit)}) · stderr ({len(stderr)})", expanded=False):
        if audit:
            st.markdown("**Tool audit (most recent 50)**")
            for entry in audit[-50:]:
                st.code(
                    f"[{entry.get('ts')}] {entry.get('tool')}\n"
                    f"{json.dumps(entry.get('input'), indent=2, default=str)}",
                    language="json",
                )
        else:
            st.caption("No tool calls yet.")
        st.divider()
        st.markdown("**Cortex Code stderr (most recent 50 lines)**")
        if stderr:
            st.code("\n".join(stderr[-50:]), language="text")
        else:
            st.caption("No stderr output.")

    if session._chat is not None:
        with st.expander("Session", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                dump_data = json.dumps(session._chat.dump(), indent=2, default=str)
                st.download_button("Save session", dump_data,
                                   file_name="session.json", mime="application/json",
                                   key="coco_save")
            with col2:
                uploaded = st.file_uploader("Restore", type="json", key="coco_restore")
                if uploaded is not None:
                    from cocosdkagent import Chat
                    d = json.loads(uploaded.read())
                    session._chat = Chat.from_dump(d)
                    st.session_state["coco_messages"].clear()
                    st.rerun()
            st.caption("Restored sessions show text history only — tool data isn't replayed.")


def _render_actions(session: AgentSession) -> None:
    cols = st.columns([1, 1, 1, 3])
    if cols[0].button(":material/stop_circle: Stop", key="coco_stop", use_container_width=True):
        session.stop()
        st.toast("Stop signal sent to agent.")
    if cols[1].button(":material/restart_alt: Clear", key="coco_clear", use_container_width=True):
        st.session_state["coco_messages"].clear()
        st.session_state["coco_audit"].clear()
        st.session_state["coco_stderr"].clear()
        st.session_state["coco_pending_prompt"] = None
        st.rerun()
    if cols[2].button(":material/close: Close", key="coco_close", use_container_width=True):
        st.session_state["coco_dialog_open"] = False
        st.rerun()


@st.dialog("Cortex Code — go deeper", width="large")
def chat_dialog(connection: str) -> None:
    _init_state()
    session = get_or_create_session(st.session_state, connection)
    _status_strip(session)

    if session.connect_error:
        st.error("Cortex Code Agent failed to connect.")
        with st.expander("Traceback", expanded=False):
            st.code(session.connect_error, language="text")
        _render_debug(session)
        return

    _render_history(session)
    _render_pills(session)

    pending = st.session_state.get("coco_pending_prompt")
    typed = st.chat_input("Ask a deeper question about the dashboard...", key="coco_input")
    prompt = pending or typed
    if prompt:
        st.session_state["coco_pending_prompt"] = None
        st.session_state["coco_in_flight"] = True
        _drain_and_render(prompt, session)
        st.session_state["coco_in_flight"] = False
        st.rerun()

    _render_actions(session)
    _render_debug(session)
