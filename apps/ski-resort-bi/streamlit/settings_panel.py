"""Sidebar settings panel — model picker, due-diligence depth, tool toggles.

Writes to ``st.session_state['coco_settings']``. ``bridge.get_or_create_session``
reads this dict on every call and rebuilds the ``Chat`` if any value changed,
so toggling settings takes effect on the next turn without an explicit Apply.
"""

from __future__ import annotations

import streamlit as st

from cortex_code_agent import (
    CORTEX_AGENTS,
    DEFAULT_AGENT_KEY,
    DEFAULT_MODEL,
    DEFAULT_PROMPT_MODE,
)

MODEL_CHOICES = [
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-opus-4-7",
    "claude-haiku-4-5",
]

DEFAULT_SETTINGS = {
    "model": DEFAULT_MODEL,
    "prompt_mode": DEFAULT_PROMPT_MODE,  # "explore" (no agent) | "agent" (DATA_AGENT_RUN accelerator)
    "show_thinking": True,
    "due_diligence": "shallow",  # off | shallow | full
    "max_evidence_steps": 5,
    "fast_path": False,  # False = SDK governed explorer (primary); True = deterministic broker
    "enabled_agents": (DEFAULT_AGENT_KEY,),
    "enabled_exploration": True,
}

# A/B prompt modes: label shown in the UI -> internal value passed to the SDK.
PROMPT_MODE_LABELS = {"Explore-only": "explore", "Agent-aware": "agent"}
PROMPT_MODE_VALUE_TO_LABEL = {v: k for k, v in PROMPT_MODE_LABELS.items()}

DUE_DILIGENCE_OPTIONS = ["off", "shallow", "full"]

TOOL_ORIGIN_GROUPS = {
    "Custom (Cortex Agents)": [
        (key, spec["display_name"], spec["description"], "agent")
        for key, spec in CORTEX_AGENTS.items()
    ],
    "Custom (exploration)": [
        ("enabled_exploration", "Semantic-view exploration",
         "list_semantic_views + describe_semantic_view for due diligence.", "exploration"),
    ],
}


def _ensure_settings() -> dict:
    s = st.session_state.get("coco_settings")
    if not isinstance(s, dict):
        s = dict(DEFAULT_SETTINGS)
        st.session_state["coco_settings"] = s
    else:
        for k, v in DEFAULT_SETTINGS.items():
            s.setdefault(k, v)
    return s


def render_settings_panel() -> None:
    """Render the settings UI in the current sidebar context."""
    s = _ensure_settings()

    st.subheader(":material/settings: Agent settings")

    # A/B explorer prompt mode (the headline experiment control).
    cur_mode_val = s.get("prompt_mode", DEFAULT_PROMPT_MODE)
    cur_label = PROMPT_MODE_VALUE_TO_LABEL.get(cur_mode_val, "Explore-only")
    new_label = st.segmented_control(
        "Explorer prompt (A/B)",
        list(PROMPT_MODE_LABELS),
        default=cur_label,
        key="coco_set_prompt_mode",
        help=(
            "Explore-only: the SDK knows only the marts and answers via SQL. "
            "Agent-aware: the SDK also knows the deployed RESORT_EXECUTIVE agent "
            "and may make one small DATA_AGENT_RUN call to fold in its answer."
        ),
    )
    if new_label:
        s["prompt_mode"] = PROMPT_MODE_LABELS[new_label]

    s["fast_path"] = st.toggle(
        "Use deterministic fast path",
        value=bool(s.get("fast_path", False)),
        key="coco_set_fast_path",
        help="Off (default): the SDK governed explorer runs its own sql_execute "
             "loop under the read-only role. On: a deterministic broker answers "
             "canned dashboard questions faster but is not real SDK exploration.",
    )

    # Model picker
    cur_model = s["model"] if s["model"] in MODEL_CHOICES else MODEL_CHOICES[0]
    new_model = st.selectbox(
        "Model",
        MODEL_CHOICES,
        index=MODEL_CHOICES.index(cur_model),
        key="coco_set_model",
        help="Used by cocosdkagent for orchestration. Cortex Agents pick "
             "their own model server-side.",
    )
    s["model"] = new_model

    # Due diligence depth
    cur_dd = s["due_diligence"] if s["due_diligence"] in DUE_DILIGENCE_OPTIONS else "shallow"
    new_dd = st.segmented_control(
        "Due diligence",
        DUE_DILIGENCE_OPTIONS,
        default=cur_dd,
        key="coco_set_dd",
        help=(
            "off: just the agent's answer. "
            "shallow: agent + 1-2 adjacent metric mentions. "
            "full: agent + describe + optional file reads."
        ),
    )
    if new_dd:
        s["due_diligence"] = new_dd

    s["max_evidence_steps"] = st.slider(
        "Max evidence steps",
        min_value=1,
        max_value=6,
        value=int(s.get("max_evidence_steps", 5)),
        help="Caps triangulation work so the BI assistant does not loop.",
        key="coco_set_max_evidence_steps",
    )

    # Show thinking
    s["show_thinking"] = st.toggle(
        "Show thinking",
        value=bool(s.get("show_thinking", True)),
        key="coco_set_thinking",
        help="When off, the assistant suppresses streamed text emitted before "
             "the first tool result.",
    )

    st.divider()
    st.caption(":material/build: Tool catalogue")

    # Per-agent toggles
    enabled = set(s.get("enabled_agents") or ())
    for key, label, desc, kind in TOOL_ORIGIN_GROUPS["Custom (Cortex Agents)"]:
        on = st.toggle(
            label,
            value=key in enabled,
            key=f"coco_set_agent_{key}",
            help=desc,
        )
        if on:
            enabled.add(key)
        else:
            enabled.discard(key)
    if not enabled:
        # Always keep at least one agent enabled to avoid a tool-less chat.
        enabled.add(DEFAULT_AGENT_KEY)
    s["enabled_agents"] = tuple(sorted(enabled))

    # Exploration toggle
    for key, label, desc, _kind in TOOL_ORIGIN_GROUPS["Custom (exploration)"]:
        s[key] = st.toggle(
            label,
            value=bool(s.get(key, True)),
            key=f"coco_set_{key}",
            help=desc,
        )

    with st.expander("Built-in (cocosdkagent)", expanded=False):
        st.caption("These are configured in `cortex_code_agent.policy.ALLOWED_TOOLS`.")
        from cortex_code_agent import ALLOWED_TOOLS
        for t in ALLOWED_TOOLS:
            st.markdown(f"- `{t}`")

    st.session_state["coco_settings"] = s
