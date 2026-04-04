"""Vector index query stub (Neo4j vector index + OpenAI embeddings — implement when index exists)."""


async def vector_search_stub(query_embedding: list[float], top_k: int = 5) -> list[str]:
    raise NotImplementedError("Create vector index and bind OpenAI embeddings.")
