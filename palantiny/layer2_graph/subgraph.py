"""APOC apoc.path.subgraphAll wrapper (requires APOC plugin)."""

SUBGRAPH_CYPHER_TEMPLATE = """
MATCH (center {herb_id: $herb_id})
CALL apoc.path.subgraphAll(center, {relationshipFilter: $rel_filter, maxLevel: $max_level})
YIELD nodes, relationships
RETURN size(nodes) AS n_nodes, size(relationships) AS n_rels
"""


async def fetch_subgraph_stats_stub(session: object, herb_id: str, max_level: int = 2) -> dict:
    """Execute SUBGRAPH_CYPHER_TEMPLATE when APOC is available."""
    raise NotImplementedError("Inject neo4j AsyncSession and run with APOC enabled.")
