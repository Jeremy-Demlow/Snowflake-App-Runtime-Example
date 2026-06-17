"""Ski-resort agent policy: chosen values passed to cocosdkagent.Chat."""
from pathlib import Path

# Governed explorer tool policy.
# We do NOT use the CLI --allowed-tools allowlist: empirically it fails to match
# `sql_execute` and blocks the explorer's primary tool. Instead we leave the
# allowlist empty and ENFORCE via PreToolUse hooks (block_tools) + the read-only
# Snowflake role, which are the reliable, callback-level guardrails.
ALLOWED_TOOLS: list[str] = []
# Noisy / write-capable / off-task tools blocked at the PreToolUse hook layer.
# `task`/`team`/`cron` matter most: without them the model spawns sub-agents that
# run bash OUTSIDE these hooks (guardrail bypass) and explode token cost.
BLOCKED_TOOLS = [
    "Write", "Edit", "Bash", "bash_output", "kill_shell",
    "task", "Task", "team", "Team", "cron", "Cron",
    "fdbt", "data_diff",
    "web_search", "web_fetch",
    "skill", "tool_search", "direct_tool_calling", "programmatic_tool_calling",
    "notebook_actions", "python_repl", "apply_patch",
]
# Kept for the CLI passthrough (best-effort; the hook is the real enforcement).
DISALLOWED_TOOLS = list(BLOCKED_TOOLS)
DEFAULT_MAX_TURNS = 8
DEFAULT_EFFORT = "medium"
DEFAULT_MODEL = "claude-sonnet-4-6"
STDERR_RING_LIMIT = 200

# A/B explorer system prompts. "explore" knows only the marts; "agent" also
# knows the deployed Cortex Agent and the DATA_AGENT_RUN accelerator recipe.
_PROMPT_DIR = Path(__file__).parent
PROMPT_FILES = {
    "explore": _PROMPT_DIR / "system_prompt_explore.md",
    "agent": _PROMPT_DIR / "system_prompt_agent.md",
}
DEFAULT_PROMPT_MODE = "explore"
# Legacy single-prompt path (kept as a fallback if the mode files are missing).
SYSTEM_PROMPT_PATH = _PROMPT_DIR / "system_prompt.md"

SKI_RESORT_DATABASE = "SKI_RESORT_DEMO"
SKI_RESORT_SEMANTIC_SCHEMA = "SEMANTIC"

# --- Governed explorer guardrails ---------------------------------------------
# Layer 1: the read-only role used by the explorer's Chat connection. Its grants
# (read-only, scoped to the ski-resort databases) are the absolute guardrail.
EXPLORER_CONNECTION = "ski_readonly"
# Layer 3: databases the explorer may reference. The role already enforces this;
# the scope inspector gives a clean, fast rejection message.
SCOPE_DATABASES = {"SKI_RESORT_DEMO", "SNOWFLAKE"}
# Layer 4: cost containment.
MAX_EXPLORER_ROWS = 1000

CORTEX_AGENTS: dict[str, dict[str, str]] = {
    "resort_executive": {
        "fqn": "SKI_RESORT_DEMO.AGENTS.RESORT_EXECUTIVE",
        "display_name": "Resort Executive",
        "description": (
            "Comprehensive BI agent: revenue, daily KPIs, customers, "
            "passholders, weather, ops, staffing, marketing, satisfaction, "
            "safety, ski school. Best for broad executive questions."
        ),
    },
    "ski_ops_assistant": {
        "fqn": "SKI_RESORT_DEMO.AGENTS.SKI_OPS_ASSISTANT",
        "display_name": "Ski Ops Assistant",
        "description": (
            "Operations-focused agent: lift wait times, maintenance, grooming, "
            "staffing coverage, weather, safety incidents."
        ),
    },
}

DEFAULT_AGENT_KEY = "resort_executive"


def load_system_prompt(prompt_mode: str = DEFAULT_PROMPT_MODE) -> str:
    """Load the explorer system prompt for the given A/B mode.

    prompt_mode: "explore" (no agent) or "agent" (DATA_AGENT_RUN accelerator).
    Falls back to the legacy single prompt if the mode file is missing.
    """
    path = PROMPT_FILES.get(prompt_mode, PROMPT_FILES[DEFAULT_PROMPT_MODE])
    if not path.exists():
        path = SYSTEM_PROMPT_PATH
    return path.read_text()
