from typing import Protocol, runtime_checkable

from palantiny.contracts.sql import PriceRow


@runtime_checkable
class HerbPriceRepositoryProtocol(Protocol):
    async def fetch_by_herb_ids(self, herb_ids: list[str]) -> list[PriceRow]: ...

    async def fetch_by_herb_names(self, names: list[str]) -> list[PriceRow]: ...


class HerbPriceRepository:
    """Stub: implement with real SQLAlchemy queries against herb_master / herb_price_item."""

    async def fetch_by_herb_ids(self, herb_ids: list[str]) -> list[PriceRow]:
        raise NotImplementedError("Wire to Postgres in a follow-up task.")

    async def fetch_by_herb_names(self, names: list[str]) -> list[PriceRow]:
        raise NotImplementedError("Wire to Postgres in a follow-up task.")
