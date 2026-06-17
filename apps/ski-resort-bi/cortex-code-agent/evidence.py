"""Shared data structures for the SDK-driven BI triangulation loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd


ProviderName = Literal["agent", "semantic_view", "sql", "process"]


@dataclass
class AgentAsset:
    fqn: str
    name: str
    comment: str = ""


@dataclass
class SemanticAsset:
    fqn: str
    name: str
    schema: str
    comment: str = ""


@dataclass
class TableAsset:
    fqn: str
    name: str
    schema: str
    kind: str = ""


@dataclass
class ProcessAsset:
    path: str
    reason: str


@dataclass
class DiscoveryResult:
    agents: list[AgentAsset] = field(default_factory=list)
    semantic_views: list[SemanticAsset] = field(default_factory=list)
    tables: list[TableAsset] = field(default_factory=list)
    process_docs: list[ProcessAsset] = field(default_factory=list)


@dataclass
class PromptIntent:
    domain: str
    is_data_question: bool
    is_driver_question: bool
    is_broad_question: bool
    is_code_question: bool
    terms: list[str] = field(default_factory=list)


@dataclass
class EvidenceStep:
    provider: ProviderName
    purpose: str
    target: str
    prompt_or_query: str
    required: bool = True


@dataclass
class EvidenceResult:
    provider: ProviderName
    target: str
    purpose: str
    text: str = ""
    sql: list[str] = field(default_factory=list)
    dataframe: pd.DataFrame | None = None
    charts: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class BIAnswer:
    text: str
    evidence: list[EvidenceResult] = field(default_factory=list)
    tables: list[pd.DataFrame] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    confidence: str = "medium"
    route_summary: str = ""
