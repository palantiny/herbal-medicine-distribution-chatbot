from dataclasses import dataclass
from enum import Enum


class CoverageCase(str, Enum):
    """Herb data presence across Neo4j (monograph-rich / stub) vs Postgres/cache."""

    BOTH = "both"
    GRAPH_ONLY_NO_DB = "graph_only_no_db"  # B: warn — no Postgres/cache rows
    DB_ONLY_NO_GRAPH = "db_only_no_graph"  # C: warn — graph miss, SQL/cache hit
    NEITHER = "neither"
    GRAPH_ONLY_PATH_NO_SQL = "graph_only_path_no_sql"  # stage2 DIRECT: SQL not run


@dataclass(frozen=True)
class CoverageNotice:
    case: CoverageCase
    lines: tuple[str, ...]
