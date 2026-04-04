from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PriceRow:
    herb_id: Optional[str]
    herb_name: Optional[str]
    payload: dict[str, Any]


@dataclass(frozen=True)
class SqlContextPack:
    """Structured SQL/cache outcome (stub for repository layer)."""

    rows: tuple[PriceRow, ...]
    source: str  # "postgres" | "redis_cache" | "empty"
