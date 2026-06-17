"""Headless harness: verify the agent-as-tool architecture without Streamlit.

Drives bridge.AgentSession directly. Reports input tokens + tool calls fired
across three scenarios:

  1. Baseline probe (no tools fired)
  2. Sales-trend question (should fire ONE call_resort_executive)
  3. Same prompt 3x (consistency check)

Run:
    SNOWFLAKE_CONNECTION_NAME=myconnection python3 streamlit/test_token_diet.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bridge import AgentSession  # noqa: E402


def run(label: str, prompt: str, conn: str) -> dict:
    print(f"\n{'=' * 60}\n{label}\nprompt: {prompt!r}\n{'=' * 60}")
    sess = AgentSession(connection=conn)
    sess.connect()
    if sess.connect_error:
        print("CONNECT FAILED:")
        print(sess.connect_error[:500])
        return {}

    t0 = time.monotonic()
    counts = {"text": 0, "tool_use": 0, "tool_result": 0, "error": 0}
    tools_fired: list[str] = []
    text_chars = 0
    for ev in sess.send_events(prompt):
        kind = ev.get("kind")
        if kind in counts:
            counts[kind] += 1
        if kind == "tool_use":
            name = ev["tool_name"]
            tools_fired.append(name)
            print(f"  -> tool_use: {name}")
        elif kind == "text":
            text_chars += len(ev.get("delta", ""))
        elif kind == "error":
            print(f"  -> ERROR: {ev.get('message')}")
        elif kind == "done":
            break
    elapsed = time.monotonic() - t0

    use = sess.usage
    out = {
        "label": label,
        "input_tokens": use.input_tokens,
        "output_tokens": use.output_tokens,
        "cache_read": use.cache_read_input_tokens,
        "cache_write": use.cache_creation_input_tokens,
        "cost_usd": use.cost_usd,
        "events": counts,
        "tools_fired": tools_fired,
        "text_chars": text_chars,
        "agent_responses": len(sess.agent_responses),
        "elapsed_s": round(elapsed, 1),
    }
    print(f"\nResult: in={out['input_tokens']:,} out={out['output_tokens']:,} "
          f"cost=${out['cost_usd']:.4f} tools={tools_fired} "
          f"agent_responses={out['agent_responses']} elapsed={out['elapsed_s']}s")
    sess.disconnect()
    return out


def main() -> int:
    conn = os.environ.get("SNOWFLAKE_CONNECTION_NAME", "myconnection")
    print(f"Connection: {conn}")

    results: list[dict] = []

    # Direct REST+SSE scenario: bypass cocosdkagent entirely, measure
    # time-to-first-byte and ensure dataframes/sql come back.
    print("\n" + "=" * 60)
    print("REST_SSE: direct call_cortex_agent (no cocosdkagent)")
    print("=" * 60)
    sys.path.insert(0, str(HERE.parent / "cortex-code-agent"))
    from agent_client import call_cortex_agent  # noqa: E402

    rest_t0 = time.monotonic()
    rest_resp = call_cortex_agent(
        "What is total ticket revenue for the 2024-2025 season?",
        agent_fqn="SKI_RESORT_DEMO.AGENTS.RESORT_EXECUTIVE",
        connection=conn,
    )
    rest_total = time.monotonic() - rest_t0
    print(f"  text: {rest_resp.text[:120]!r}")
    print(f"  tools_used: {rest_resp.tools_used}")
    print(f"  sql queries: {len(rest_resp.sql_queries)}")
    print(f"  dataframes: {len(rest_resp.dataframes)}")
    print(f"  statuses: {len(rest_resp.statuses)} events")
    print(f"  TIME_TO_FIRST_BYTE: {rest_resp.time_to_first_byte}s")
    print(f"  TOTAL: {rest_resp.duration_seconds}s (wall: {rest_total:.1f}s)")

    # Assertions for fail-fast feedback
    assert rest_resp.text, "REST_SSE: empty text response"
    assert rest_resp.dataframes, "REST_SSE: no dataframes returned"
    assert rest_resp.time_to_first_byte < 5.0, (
        f"REST_SSE: time_to_first_byte={rest_resp.time_to_first_byte}s exceeds 5s budget"
    )
    print("  [OK] all REST_SSE assertions passed")

    results.append(run(
        "BASELINE (no tools)",
        "Reply with just the number: 1+1=?",
        conn,
    ))

    results.append(run(
        "AGENT_TOOL: sales trend",
        "Why are my sales trending up and seemingly a little bit more spikey as well?",
        conn,
    ))

    # Consistency check: same prompt three times, eyeball variance
    print("\n" + "=" * 60)
    print("CONSISTENCY CHECK: same prompt x3")
    print("=" * 60)
    consistency_runs: list[dict] = []
    for i in range(3):
        r = run(
            f"CONSISTENCY #{i + 1}",
            "What is total ticket revenue for the 2024-2025 season?",
            conn,
        )
        consistency_runs.append(r)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(
        f"{'REST_SSE direct':30s}  "
        f"ttfb={rest_resp.time_to_first_byte}s  "
        f"total={rest_resp.duration_seconds}s  "
        f"sql={len(rest_resp.sql_queries)}  "
        f"dfs={len(rest_resp.dataframes)}"
    )
    for r in results + consistency_runs:
        if not r:
            continue
        print(
            f"{r['label']:30s}  "
            f"in={r['input_tokens']:>7,}  "
            f"out={r['output_tokens']:>5,}  "
            f"${r['cost_usd']:.4f}  "
            f"{r['elapsed_s']}s  "
            f"tools={r['tools_fired']}"
        )

    print("\nExpected vs. pre-fix 250,188 input tokens:")
    if results and len(results) >= 2 and results[1].get("input_tokens"):
        v = results[1]["input_tokens"]
        delta = 250188 - v
        pct = 100 * delta / 250188
        print(f"  delta = {delta:+,} ({pct:+.1f}%) — agent-tool turn used {v:,}")

    if len(consistency_runs) >= 2:
        sizes = [r.get("text_chars", 0) for r in consistency_runs if r]
        if sizes:
            spread = max(sizes) - min(sizes)
            print(f"\nConsistency: text_chars min={min(sizes)} max={max(sizes)} spread={spread}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
