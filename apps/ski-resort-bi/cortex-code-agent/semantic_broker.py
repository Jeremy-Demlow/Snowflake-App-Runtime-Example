"""SDK-driven BI triangulation broker.

This is the deterministic entry point for Streamlit dashboard questions. It
discovers available BI assets, plans one or more evidence paths, executes them,
then reconciles the evidence into a final answer with trace.
"""
from __future__ import annotations

try:
    from .discovery import discover_all
    from .evidence import BIAnswer, DiscoveryResult, EvidenceResult, EvidenceStep, PromptIntent
    from .evidence_planner import classify_prompt, plan_evidence
    from .providers import run_provider
    from .reconciler import reconcile
except ImportError:
    from discovery import discover_all
    from evidence import BIAnswer, DiscoveryResult, EvidenceResult, EvidenceStep, PromptIntent
    from evidence_planner import classify_prompt, plan_evidence
    from providers import run_provider
    from reconciler import reconcile


def should_handle_with_broker(prompt: str) -> bool:
    intent = classify_prompt(prompt)
    return intent.is_data_question or intent.is_code_question


def run_semantic_turn(
    prompt: str,
    *,
    connection: str,
    settings: dict | None = None,
    discovery: DiscoveryResult | None = None,
) -> BIAnswer:
    settings = settings or {}
    discovery = discovery or discover_all(connection, prompt=prompt)
    intent, steps = plan_evidence(prompt, discovery, settings)

    max_steps = int(settings.get("max_evidence_steps", 4))
    results: list[EvidenceResult] = []
    for step in steps[:max_steps]:
        results.append(run_provider(step, connection))

    return reconcile(prompt, intent, results)


__all__ = [
    "BIAnswer",
    "DiscoveryResult",
    "EvidenceResult",
    "EvidenceStep",
    "PromptIntent",
    "classify_prompt",
    "discover_all",
    "plan_evidence",
    "run_semantic_turn",
    "should_handle_with_broker",
]
