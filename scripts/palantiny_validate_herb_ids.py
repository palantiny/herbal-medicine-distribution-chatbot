#!/usr/bin/env python3
"""
모노그래프 *.cypher.txt 의 (herb_name, herb_id) 와
data/herb_prices_from_csv.cypher 의 MERGE (h:Herb {name}) 집합을 비교합니다.

  python scripts/palantiny_validate_herb_ids.py
  python scripts/palantiny_validate_herb_ids.py --fail-on-mismatch
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
    parser = argparse.ArgumentParser(description="Palantiny: herb_id / name reconciliation")
    parser.add_argument("--monograph-root", type=Path, default=root / "data" / "herb_monograph_chapters")
    parser.add_argument("--price-cypher", type=Path, default=root / "data" / "herb_prices_from_csv.cypher")
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="monograph_only 또는 price_only 가 하나라도 있으면 exit 1",
    )
    args = parser.parse_args()

    from palantiny.data_sync.manifest import (
        load_monograph_herb_entries,
        load_price_cypher_herb_names,
        monograph_name_to_id_map,
    )
    from palantiny.data_sync.reconcile import reconcile_sets

    entries = load_monograph_herb_entries(args.monograph_root)
    mono_names = {n for n, _ in entries}
    price_names = load_price_cypher_herb_names(args.price_cypher)
    r = reconcile_sets(mono_names, price_names)
    id_map = monograph_name_to_id_map(entries)

    print(f"monograph files (pairs): {len(entries)}")
    print(f"price_cypher distinct Herb names: {len(price_names)}")
    print(f"intersection: {len(r.both_names)}")
    print(f"monograph_only: {len(r.monograph_only_names)}")
    print(f"price_only (CSV graph, may need stub): {len(r.price_only_names)}")

    # 이름은 양쪽에 있는데 herb_id 정합성은 별도(모노그래프 주석 기준)
    for name in sorted(r.both_names)[:5]:
        print(f"  sample both: {name} -> {id_map.get(name, '?')}")

    if args.fail_on_mismatch and (r.monograph_only_names or r.price_only_names):
        print("[실패] 집합 불일치가 있습니다. --fail-on-mismatch", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
