#!/usr/bin/env python3
"""
CSV → PostgreSQL 적재 스캐폴드.

현재: pandas로 행 수·헤더 검증만 수행. 컬럼 매핑 후 `herb_price_item` 등에 to_sql 연결은 후속 작업.

  python scripts/palantiny_load_postgres.py
  python scripts/palantiny_load_postgres.py --csv data/herb_price_korea.csv
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
    parser = argparse.ArgumentParser(description="Palantiny: validate herb price CSV for Postgres load")
    parser.add_argument(
        "--csv",
        type=Path,
        default=root / "data" / "herb_price_korea.csv",
        help="가격 CSV 경로",
    )
    args = parser.parse_args()
    if not args.csv.is_file():
        print(f"[오류] 파일 없음: {args.csv}", file=sys.stderr)
        return 1

    from palantiny.layer1_rdb.loaders.csv_to_postgres import load_herb_price_csv_stub

    n = load_herb_price_csv_stub(args.csv)
    print(f"OK: {args.csv} — pandas로 읽은 데이터 행 수 ≈ {n}")
    print("(실제 DB 적재는 엔진·테이블 매핑 구현 후 load_herb_price_csv_stub에 engine 전달)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
