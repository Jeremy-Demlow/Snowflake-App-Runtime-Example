# cortex-code-agent

Agent configuration for the Streamlit-embedded Cortex Code chat (REQ-014).

This folder is **local-only** (gitignored). The UI lives in `../streamlit/`.

## What's here

| File | Purpose |
| --- | --- |
| `system_prompt.md` | Role + read-only mandate, appended to the SDK preset prompt |
| `agent_options.py` | `build_options(connection, abort_event, audit_list, ...)` |
| `hooks.py` | `sql_guard` (PreToolUse), `make_audit_hook` (PostToolUse) |
| `__init__.py` | Re-exports |

## Boundary

All control flow is through the Cortex Code Agent SDK Python API:

```python
from cortex_code_agent_sdk import CortexCodeSDKClient
from cortex_code_agent import build_options

options = build_options(connection="myconnection", abort_event=ev, audit_list=audits)
async with CortexCodeSDKClient(options) as client:
    await client.query("show me revenue last week")
    async for msg in client.receive_response():
        ...
```

The SDK's default transport spawns the `cortex` CLI as a subprocess. We do
not invoke the CLI ourselves anywhere.

## Guardrails

- `allowed_tools = ["Read", "Glob", "Grep", "SQL"]`
- `disallowed_tools = ["Write", "Edit", "Bash"]`
- `max_turns = 8`, `effort = "medium"`, `model = "auto"`
- PreToolUse hook on `SQL`: blocks any query containing
  `CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|MERGE|TRUNCATE|COPY|GRANT|REVOKE`
- PostToolUse hook on every tool: appends a redacted record to a session list
  rendered in the chat panel's "Tool audit" expander
