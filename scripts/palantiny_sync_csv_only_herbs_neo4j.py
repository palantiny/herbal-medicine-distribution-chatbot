#!/usr/bin/env python3
"""
가격 Cypher에만 등장하는 Herb 이름(CSV 쪽)에 대해 Neo4j용 스텁 MERGE 스크립트를 생성합니다.
모노그래프에 이미 있는 이름은 동일 herb_id를 사용하고, 나머지는 H_CSV_* 해시 ID를 씁니다.

  python scripts/palantiny_sync_csv_only_herbs_neo4j.py
  python scripts/palantiny_sync_csv_only_herbs_neo4j.py -o data/herb_csv_only_stubs.cypher

Neo4j 적용(선택): 생성된 .cypher를 cypher-shell 로 실행.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


_ROOT = _root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    root = _root()
    parser = argparse.ArgumentParser(description="Palantiny: write Neo4j stub MERGE for CSV-only herbs")
    parser.add_argument("--monograph-root", type=Path, default=root / "data" / "herb_monograph_chapters")
    parser.add_argument("--price-cypher", type=Path, default=root / "data" / "herb_prices_from_csv.cypher")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=root / "data" / "herb_csv_only_stubs.cypher",
    )
    args = parser.parse_args()

    from palantiny.data_sync.manifest import (
        load_monograph_herb_entries,
        load_price_cypher_herb_names,
        monograph_name_to_id_map,
    )
    from palantiny.data_sync.reconcile import reconcile_sets
    from palantiny.data_sync.neo4j_stub_sync import write_stub_cypher_file

    entries = load_monograph_herb_entries(args.monograph_root)
    mono_names = {n for n, _ in entries}
    price_names = load_price_cypher_herb_names(args.price_cypher)
    r = reconcile_sets(mono_names, price_names)
    id_map = monograph_name_to_id_map(entries)

    count = write_stub_cypher_file(sorted(r.price_only_names), args.output, name_to_id=id_map)
    print(f"Wrote {count} stub MERGE blocks -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
