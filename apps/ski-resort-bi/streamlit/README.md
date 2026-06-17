# streamlit (REQ-014 — embedded Cortex Code chat)

Local-only Streamlit app that pairs a ski-resort gold-KPI dashboard with a
floating chat panel powered by the **Cortex Code Agent SDK** (Python).

Folder is gitignored. Sibling folder `../cortex-code-agent/` holds the agent
configuration, hooks, and system prompt.

## Run

Prerequisite: `cortex` CLI on PATH (the SDK uses it as a subprocess transport).

```bash
curl -LsS https://ai.snowflake.com/static/cc-scripts/install.sh | sh
pip install -r /Users/jdemlow/00_Code/github/AgentMangement/streamlit/requirements.txt
SNOWFLAKE_CONNECTION_NAME=myconnection \
  streamlit run /Users/jdemlow/00_Code/github/AgentMangement/streamlit/app.py
```

## Files

| File | Role |
| --- | --- |
| `app.py` | Page entry, sidebar connection picker, layout |
| `dashboard.py` | KPI cards + line/bar charts against `SKI_RESORT_DEMO.MARTS.*` |
| `chat_panel.py` | `FloatingContainer` UI + message history + audit expander |
| `bridge.py` | `AgentSession` — sync↔async glue around `CortexCodeSDKClient` |
| `_bootstrap.py` | Loads sibling `cortex-code-agent/` as the `cortex_code_agent` import |
| `requirements.txt` | Pinned deps |

## Architecture

```
Streamlit (sync, per-rerun)
   └── chat_panel.render_chat_panel()
        └── bridge.get_or_create_session()  ── stored in st.session_state
              └── AgentSession
                   ├── asyncio loop on daemon thread
                   ├── CortexCodeSDKClient (Python SDK)  ──▶ cortex CLI subprocess ──▶ Snowflake
                   ├── PreToolUse SQL guard  (cortex-code-agent/hooks.py)
                   └── PostToolUse audit hook → st.session_state["coco_audit"]
```

All control flow is through the SDK API (`client.connect / query /
receive_response / interrupt / disconnect`). We never invoke the CLI directly.

## Smoke checks

1. App opens and dashboard renders three KPIs (or warning toasts if marts
   aren't reachable from the current role).
2. Click the floating chat icon, ask `"show me revenue last 7 days"` →
   assistant response with at least one row in the Tool audit expander
   tagged `SQL`.
3. Ask `"drop fact_revenue"` → assistant returns a denial; no SQL executed
   (audit list does *not* gain a SQL row for this attempt).
4. Click **Stop** mid-stream → response ends; UI returns to idle.

## SiS swap path (future REQ)

When promoting to Streamlit-in-Snowflake:

- Replace `bridge.AgentSession` with a thin Cortex Agents REST client.
- Drop `Read/Glob/Grep` tools (no host filesystem in SiS); keep a narrow SQL
  tool fronted by a stored procedure that enforces the same read-only guard.
- `chat_panel.py` and `dashboard.py` remain unchanged.
