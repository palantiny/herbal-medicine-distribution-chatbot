"""
CSV → PostgreSQL bulk load (scaffold).

Full ingest should map multi-header price CSVs to herb_price_item; this stub validates paths
and documents the intended pandas → COPY/to_sql flow.
"""

from pathlib import Path
from typing import Any, Optional

import pandas as pd


def read_price_csv(path: Path, header_rows: list[int] | None = None) -> pd.DataFrame:
    """Read herb_price_korea/foreign style CSV with multi-row headers."""
    if header_rows is None:
        header_rows = [0, 1, 2]
    return pd.read_csv(path, header=header_rows, encoding="utf-8-sig")


def load_herb_price_csv_stub(
    csv_path: Path,
    *,
    engine: Any = None,
    table_name: str = "herb_price_item",
) -> int:
    """
    Placeholder row count after read. When `engine` is set, use df.to_sql(..., if_exists='append').

    Returns number of logical product rows attempted (0 if file missing).
    """
    if not csv_path.is_file():
        return 0
    df = read_price_csv(csv_path)
    # Without engine, only validate readability
    if engine is None:
        return len(df.index)
    raise NotImplementedError("Provide SQLAlchemy engine and column mapping in production.")
