"""Palantiny maintenance CLI (validate stubs, etc.)."""

import argparse
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


_R = _repo_root()
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="palantiny")
    sub = parser.add_subparsers(dest="cmd")

    p_val = sub.add_parser("validate-herb-ids", help="Run herb id reconciliation report")
    p_val.add_argument("--monograph-root", type=Path, default=None)
    p_val.add_argument("--price-cypher", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.cmd == "validate-herb-ids":
        root = args.monograph_root or _repo_root() / "data" / "herb_monograph_chapters"
        price = args.price_cypher or _repo_root() / "data" / "herb_prices_from_csv.cypher"
        from palantiny.data_sync.manifest import (
            load_monograph_herb_entries,
            load_price_cypher_herb_names,
        )
        from palantiny.data_sync.reconcile import reconcile_sets

        entries = load_monograph_herb_entries(root)
        mono_names = {n for n, _ in entries}
        price_names = load_price_cypher_herb_names(price)
        r = reconcile_sets(mono_names, price_names)
        print(f"monograph herbs: {r.monograph_pairs}")
        print(f"price MERGE Herb names: {r.price_herb_nodes}")
        print(f"both: {len(r.both_names)}")
        mo = sorted(r.monograph_only_names)
        po = sorted(r.price_only_names)
        print(f"monograph_only ({len(mo)}): {mo[:30]}{'...' if len(mo) > 30 else ''}")
        print(f"price_only ({len(po)}): {po[:30]}{'...' if len(po) > 30 else ''}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
