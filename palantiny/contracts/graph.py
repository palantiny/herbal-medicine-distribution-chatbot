from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SimilarityResult:
    """Vector hit against a graph node (stub for future vector index)."""

    node_id: str
    score: float
    labels: tuple[str, ...]
    properties: dict[str, Any]


@dataclass(frozen=True)
class SubgraphContext:
    """APOC subgraph summary (stub)."""

    center_id: str
    cypher_snippet: str
    text_summary: str


@dataclass(frozen=True)
class GraphSearchOutcome:
    raw_context: str
    herb_name: Optional[str] = None
    herb_ids: tuple[str, ...] = ()
