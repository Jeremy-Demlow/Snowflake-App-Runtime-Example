"""Sync bridge between Streamlit and the Cortex Code Agent SDK.

Uses ``cocosdkagent.Chat.stream()`` for typed-message iteration with inline
usage tracking. Hooks (read-only SQL guard, audit logger) come from the
library; policy values (allowed tools, system prompt) come from cortex-code-agent.

The chat is configured to call our Cortex Agents (RESORT_EXECUTIVE,
SKI_OPS_ASSISTANT) plus light-weight exploration tools so the model can do
due diligence around the agent's canonical answer.
"""

from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_DIR = Path(__file__).resolve().parent
for p in (str(REPO_ROOT), str(STREAMLIT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import _bootstrap  # noqa: E402

_bootstrap.install()

from cocosdkagent import (  # noqa: E402
    Chat,
    Message,
    Usage,
    UserTurn,
    ToolResult,
    ToolUseBlock,
    UserMessage,
    ResultMessage,
    ToolResultBlock,
    sql_read_only_guard,
    audit_to_list,
    block_tools,
)
from cocosdkagent.core import _block_text  # noqa: E402

from cortex_code_agent import (  # noqa: E402
    ALLOWED_TOOLS,
    DEFAULT_AGENT_KEY,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_PROMPT_MODE,
    DISALLOWED_TOOLS,
    BLOCKED_TOOLS,
    EXPLORER_CONNECTION,
    SCOPE_DATABASES,
    STDERR_RING_LIMIT,
    AgentResponse,
    load_system_prompt,
)
from cortex_code_agent.guardrails import scope_guard  # noqa: E402


def _make_stderr_callback(buffer: list[str], limit: int = STDERR_RING_LIMIT):
    def _cb(line: str) -> None:
        buffer.append(line)
        if len(buffer) > limit:
            del buffer[: len(buffer) - limit]
        # Also stream to the process stderr so SYSTEM$GET_SERVICE_LOGS captures
        # the explorer's CLI output in-container (the Debug tab is only visible
        # in the browser, which makes remote diagnosis impossible otherwise).
        print(f"[explorer] {line}", file=sys.stderr, flush=True)
    return _cb


@dataclass
class AgentSession:
    """Owns a ``cocosdkagent.Chat`` plus shared audit/stderr/agent state."""

    connection: str
    audit: list[dict[str, Any]] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    agent_responses: dict[str, AgentResponse] = field(default_factory=dict)
    last_response_id: str | None = None
    last_thread_id: str | None = None
    last_message_id: str | None = None
    last_agent_status: str | None = None
    connect_error: str | None = None
    enabled_agents: tuple[str, ...] = (DEFAULT_AGENT_KEY,)
    enabled_exploration: bool = True
    model: str = DEFAULT_MODEL
    prompt_mode: str = DEFAULT_PROMPT_MODE
    _chat: Chat | None = None
    _connected: bool = False

    @property
    def usage(self) -> Usage:
        return self._chat.use if self._chat is not None else Usage()

    def connect(self) -> None:
        if self._connected:
            return
        try:
            # NOTE: custom `tools=` callables are silently dropped by the Cortex
            # Code CLI (it does not load type:"sdk" MCP entries), so we register
            # none. The explorer reaches the deployed agent via the DATA_AGENT_RUN
            # SQL recipe in the agent-aware system prompt, and lists semantic views
            # via INFORMATION_SCHEMA / SEMANTIC_VIEW SQL.
            self._chat = Chat(
                model=self.model,
                sp=None,
                cwd=str(REPO_ROOT),
                connection=self.connection,
                effort=DEFAULT_EFFORT,
                max_turns=DEFAULT_MAX_TURNS,
                allowed_tools=ALLOWED_TOOLS,
                disallowed_tools=DISALLOWED_TOOLS,
                permission_mode="default",
                system_prompt={"type": "preset", "append": load_system_prompt(self.prompt_mode)},
                no_mcp=True,
                sql_format="json",
                # Empty setting_sources suppresses the "CORTEX_CODE database does
                # not exist" auto-apply warning on accounts without that database.
                setting_sources=[],
                stderr=_make_stderr_callback(self.stderr),
            )
            # Guardrails (defense in depth; the read-only role is layer 1).
            # block_tools is the reliable callback-level enforcement for the
            # noisy/write-capable set (the CLI --disallowed-tools flag is best-effort).
            self._chat.on("PreToolUse")(block_tools(BLOCKED_TOOLS))
            self._chat.on("PreToolUse", matcher="sql_execute")(sql_read_only_guard())
            self._chat.on("PreToolUse", matcher="sql_execute")(
                scope_guard(SCOPE_DATABASES)
            )
            self._chat.on("PostToolUse")(audit_to_list(self.audit))
            self._chat._ensure()
            self._connected = True
        except Exception:
            self.connect_error = traceback.format_exc()
            self._connected = False
            print(f"[explorer] CONNECT FAILED:\n{self.connect_error}", file=sys.stderr, flush=True)

    def stop(self) -> None:
        if self._chat is None or not self._connected:
            return
        try:
            self._chat.interrupt()
        except Exception:
            pass

    def disconnect(self) -> None:
        if self._chat is not None and self._connected:
            try:
                self._chat.close()
            except Exception:
                pass
        self._connected = False

    def send_events(self, prompt: str) -> Iterator[dict[str, Any]]:
        """Send a prompt and yield ChatEvent dicts synchronously.

        ChatEvent kinds:
          - ``{"kind": "heartbeat"}`` 1Hz tick while the agent is thinking.
          - ``{"kind": "text", "delta": str}``
          - ``{"kind": "tool_use", "tool_name": str, "tool_input": dict, "tool_use_id": str}``
          - ``{"kind": "tool_result", "tool_use_id": str, "tool_result": str, "is_error": bool}``
          - ``{"kind": "error", "message": str}``
          - ``{"kind": "done", "message": str}``
        """
        if not self._connected:
            self.connect()
        if self.connect_error or self._chat is None:
            yield {"kind": "error", "message": "Agent not connected. See Debug expander."}
            yield {"kind": "done", "message": "not_connected"}
            return

        last_pulse = time.monotonic()
        try:
            for piece in self._chat.stream(prompt):
                events = _piece_to_events(piece)
                for ev in events:
                    yield ev
                now = time.monotonic()
                if now - last_pulse >= 1.0:
                    yield {"kind": "heartbeat"}
                    last_pulse = now
        except Exception as exc:
            yield {"kind": "error", "message": f"Bridge error: {exc}"}

        yield {"kind": "done", "message": "done"}


def _piece_to_events(piece: Any) -> list[dict[str, Any]]:
    """Convert a typed message from chat.stream() into our event-dict format."""
    events: list[dict[str, Any]] = []

    if isinstance(piece, Message):
        if piece.text:
            events.append({"kind": "text", "delta": piece.text})
        m = piece.m
        if hasattr(m, "content"):
            for block in m.content:
                if isinstance(block, ToolUseBlock):
                    events.append({
                        "kind": "tool_use",
                        "tool_name": block.name,
                        "tool_input": block.input or {},
                        "tool_use_id": block.id,
                    })

    elif isinstance(piece, ToolUseBlock):
        events.append({
            "kind": "tool_use",
            "tool_name": piece.name,
            "tool_input": piece.input or {},
            "tool_use_id": piece.id,
        })

    elif isinstance(piece, UserMessage):
        content = getattr(piece, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, ToolResultBlock):
                    events.append({
                        "kind": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "tool_result": _block_text(block),
                        "is_error": bool(block.is_error),
                    })

    elif isinstance(piece, ResultMessage):
        if piece.is_error and piece.result:
            events.append({"kind": "error", "message": f"{piece.subtype}: {piece.result}"})

    return events


def get_or_create_session(state: dict, connection: str) -> AgentSession:
    """Idempotent session getter for ``st.session_state``.

    The explorer ALWAYS connects via the read-only role connection
    (``EXPLORER_CONNECTION``) regardless of the sidebar connection, so the
    SDK's sql_execute is governed at the data layer. The sidebar connection is
    used only for the dashboard KPIs, not the chat explorer.

    Reads optional settings from ``state['coco_settings']``:
      - enabled_agents: tuple[str, ...] of CORTEX_AGENTS keys
      - enabled_exploration: bool
      - model: str
    """
    audit = state.setdefault("coco_audit", [])
    stderr = state.setdefault("coco_stderr", [])
    explorer_connection = EXPLORER_CONNECTION

    settings = state.get("coco_settings", {}) or {}
    enabled_agents = tuple(settings.get("enabled_agents") or (DEFAULT_AGENT_KEY,))
    enabled_exploration = bool(settings.get("enabled_exploration", True))
    model = settings.get("model") or DEFAULT_MODEL
    prompt_mode = settings.get("prompt_mode") or DEFAULT_PROMPT_MODE

    sess = state.get("coco_session")
    if (
        isinstance(sess, AgentSession)
        and sess._connected
        and sess.connection == explorer_connection
        and sess.audit is audit
        and sess.stderr is stderr
        and sess.enabled_agents == enabled_agents
        and sess.enabled_exploration == enabled_exploration
        and sess.model == model
        and sess.prompt_mode == prompt_mode
    ):
        return sess
    if isinstance(sess, AgentSession):
        sess.disconnect()
    sess = AgentSession(
        connection=explorer_connection,
        audit=audit,
        stderr=stderr,
        enabled_agents=enabled_agents,
        enabled_exploration=enabled_exploration,
        model=model,
        prompt_mode=prompt_mode,
    )
    sess.connect()
    state["coco_session"] = sess
    return sess
