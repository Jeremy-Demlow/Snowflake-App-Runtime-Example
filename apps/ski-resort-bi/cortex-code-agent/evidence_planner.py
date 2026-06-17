"""Rule-based evidence planner for the BI triangulation loop."""
from __future__ import annotations

try:
    from .evidence import DiscoveryResult, EvidenceStep, PromptIntent
except ImportError:
    from evidence import DiscoveryResult, EvidenceStep, PromptIntent


DOMAIN_TERMS = {
    "revenue": ["revenue", "sales", "ticket", "f&b", "food", "beverage", "rental", "uptick"],
    "visitation": ["visit", "visitor", "scan", "traffic", "attendance"],
    "operations": ["lift", "wait", "groom", "maintenance", "operation"],
    "weather": ["weather", "snow", "powder", "storm", "wind", "temperature"],
    "marketing": ["marketing", "campaign", "conversion", "promotion"],
}

CODE_TERMS = ["file", "code", "streamlit", "implementation", "where is", "how is", "repo", "function"]
WHY_TERMS = ["why", "cause", "causing", "driver", "driving", "because", "uptick", "spike", "spikey", "trend"]
BROAD_TERMS = ["executive", "leadership", "complete", "overall", "summary", "readout", "recommend"]


def classify_prompt(prompt: str) -> PromptIntent:
    lower = prompt.lower()
    matched_domains: list[str] = []
    terms: list[str] = []
    for domain, domain_terms in DOMAIN_TERMS.items():
        hits = [t for t in domain_terms if t in lower]
        if hits:
            matched_domains.append(domain)
            terms.extend(hits)
    is_code = any(t in lower for t in CODE_TERMS)
    domain = matched_domains[0] if matched_domains else ("code" if is_code else "general")
    return PromptIntent(
        domain=domain,
        is_data_question=bool(matched_domains) and not is_code,
        is_driver_question=any(t in lower for t in WHY_TERMS),
        is_broad_question=any(t in lower for t in BROAD_TERMS) or len(set(matched_domains)) >= 3,
        is_code_question=is_code and not matched_domains,
        terms=sorted(set(terms)),
    )


def _find_semantic(discovery: DiscoveryResult, *names: str) -> str | None:
    targets = {n.upper() for n in names}
    for sv in discovery.semantic_views:
        if sv.name.upper() in targets:
            return sv.fqn
    return None


def _find_agent(discovery: DiscoveryResult, name: str) -> str | None:
    target = name.upper()
    for agent in discovery.agents:
        if agent.name.upper() == target:
            return agent.fqn
    return None


def plan_evidence(prompt: str, discovery: DiscoveryResult, settings: dict | None = None) -> tuple[PromptIntent, list[EvidenceStep]]:
    settings = settings or {}
    intent = classify_prompt(prompt)
    steps: list[EvidenceStep] = []

    if intent.is_code_question:
        steps.append(EvidenceStep(
            provider="process",
            purpose="Inspect app/repo context related to the question.",
            target="repo_context",
            prompt_or_query=prompt,
        ))
        return intent, steps

    if not intent.is_data_question:
        agent = _find_agent(discovery, "RESORT_EXECUTIVE")
        if agent:
            steps.append(EvidenceStep("agent", "General resort BI answer.", agent, prompt))
        return intent, steps

    # Primary semantic evidence.
    if intent.domain == "revenue":
        sv = _find_semantic(discovery, "SEM_REVENUE")
        if sv:
            steps.append(EvidenceStep(
                provider="semantic_view",
                purpose="Canonical revenue trend and breakdown from semantic view.",
                target=sv,
                prompt_or_query=prompt,
            ))
        steps.append(EvidenceStep(
            provider="sql",
            purpose="Raw fact-table sanity check for recent revenue movement.",
            target="SKI_RESORT_DEMO.MARTS revenue facts",
            prompt_or_query="revenue_recent_sanity",
            required=False,
        ))
    elif intent.domain == "visitation":
        sv = _find_semantic(discovery, "SEM_DAILY_SUMMARY", "SEM_CUSTOMER_BEHAVIOR")
        if sv:
            steps.append(EvidenceStep("semantic_view", "Canonical visitation signal.", sv, prompt))
    elif intent.domain == "operations":
        sv = _find_semantic(discovery, "SEM_OPERATIONS")
        if sv:
            steps.append(EvidenceStep("semantic_view", "Operations metric answer.", sv, prompt))
    else:
        sv = _find_semantic(discovery, "SEM_DAILY_SUMMARY")
        if sv:
            steps.append(EvidenceStep("semantic_view", "Dashboard KPI answer.", sv, prompt))

    # Driver questions deserve adjacent evidence, not loops.
    if intent.is_driver_question:
        agent = _find_agent(discovery, "RESORT_EXECUTIVE")
        if agent:
            steps.append(EvidenceStep(
                "agent",
                "Narrative driver synthesis from the deployed resort BI agent.",
                agent,
                prompt,
                required=False,
            ))

    if intent.is_driver_question and settings.get("due_diligence", "shallow") != "off":
        adjacent_added = 0
        adjacent_limit = int(settings.get("max_due_diligence_steps", 2))
        for name, purpose in [
            ("SEM_DAILY_SUMMARY", "Check recent visitation/weekend/holiday context."),
            ("SEM_WEATHER_ANALYTICS", "Check weather and powder-day context."),
            ("SEM_MARKETING_ANALYTICS", "Check campaign context."),
        ]:
            sv = _find_semantic(discovery, name)
            if sv and all(step.target != sv for step in steps):
                steps.append(EvidenceStep("semantic_view", purpose, sv, prompt, required=False))
                adjacent_added += 1
            if adjacent_added >= adjacent_limit:
                break

    # Broad executive synthesis can use an agent as an additional evidence layer.
    agent_policy = settings.get("agent_policy", "when_needed")
    if intent.is_broad_question or agent_policy == "always":
        agent = _find_agent(discovery, "RESORT_EXECUTIVE")
        if agent:
            steps.append(EvidenceStep("agent", "Broad cross-domain synthesis.", agent, prompt, required=False))

    if not steps:
        agent = _find_agent(discovery, "RESORT_EXECUTIVE")
        if agent:
            steps.append(EvidenceStep("agent", "No semantic match; use deployed BI agent.", agent, prompt))

    return intent, steps
