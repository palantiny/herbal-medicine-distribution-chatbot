"""Join graph-derived herb_ids with SQL rows (application-layer join)."""

from palantiny.contracts.sql import PriceRow
from palantiny.layer1_rdb.repository import HerbPriceRepositoryProtocol


async def join_prices_for_herbs(
    repo: HerbPriceRepositoryProtocol,
    herb_ids: list[str],
) -> list[PriceRow]:
    return await repo.fetch_by_herb_ids(herb_ids)
