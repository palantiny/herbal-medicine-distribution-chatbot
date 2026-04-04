from typing import Any, Optional

from neo4j import AsyncDriver, AsyncGraphDatabase


class Neo4jClient:
    """Thin async session wrapper (optional; app uses graph_service)."""

    def __init__(self, driver: AsyncDriver, database: str = "neo4j"):
        self._driver = driver
        self._database = database

    async def run_read(self, cypher: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        params = params or {}
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, params)
            return [dict(r) async for r in result]


def get_driver_from_settings() -> Optional[AsyncDriver]:
    from palantiny.config.settings import get_palantiny_settings

    s = get_palantiny_settings()
    if not s.neo4j_uri:
        return None
    return AsyncGraphDatabase.driver(
        s.neo4j_uri,
        auth=(s.neo4j_username, s.neo4j_password),
    )
