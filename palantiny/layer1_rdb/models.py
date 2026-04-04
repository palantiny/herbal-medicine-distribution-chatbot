"""Logical models for CSV/herb_price_item alignment (not full ORM mapping)."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class HerbMasterRow:
    herb_id: str
    name: str
    origin: Optional[str] = None
    efficacy: Optional[str] = None


@dataclass
class HerbPriceItemRow:
    """Mirrors herb_price_item-style columns used in Text-to-SQL prompts."""

    code: Optional[str]
    herb_name: str
    origin: Optional[str]
    price_per_geun: Optional[float] = None
