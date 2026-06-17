"""Make hyphenated `cortex-code-agent/` importable as `cortex_code_agent`.

Streamlit's `streamlit run app.py` adds the script directory to sys.path. We
register the sibling `cortex-code-agent/` directory under the underscore name
so `from cortex_code_agent import ALLOWED_TOOLS` works.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_AGENT_DIR = _REPO_ROOT / "cortex-code-agent"


def install() -> None:
    if "cortex_code_agent" in sys.modules:
        return
    init_py = _AGENT_DIR / "__init__.py"
    if not init_py.exists():
        raise RuntimeError(f"cortex-code-agent package not found at {_AGENT_DIR}")
    spec = importlib.util.spec_from_file_location(
        "cortex_code_agent",
        init_py,
        submodule_search_locations=[str(_AGENT_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cortex_code_agent"] = module
    spec.loader.exec_module(module)
