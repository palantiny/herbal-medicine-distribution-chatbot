import sqlite3
import os
import re
import pandas as pd  # pylint: disable=import-error
from sqlalchemy import create_engine  # pylint: disable=import-error

# ==========================================
# 1. 파일 경로 및 DB 세팅 (raw_data 폴더 기준)
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'app', 'raw_data')

SCHEMA_FILE = os.path.join(DATA_DIR, 'djmedi_medicine_scheme.sql')
SQL_DATA_FILES = [
    os.path.join(DATA_DIR, 'djmedi_maker_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicine_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicine_dj_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicineNHIS_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicineuse_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_warehouse_data.sql')
]

CSV_DOMESTIC_FILE = os.path.join(DATA_DIR, '(원외탕전실용)한약재가격표종합 - 국산.csv')
CSV_IMPORTED_FILE = os.path.join(DATA_DIR, '(원외탕전실용)한약재가격표종합 - 수입.csv')

PG_DB_URL = "postgresql://palantiny:palantiny_secret@localhost:5432/palantiny_db"

STAGING_DB = os.path.join(BASE_DIR, 'temp_staging.db')

# ==========================================
# 2. 파서 및 클리너 함수
# ==========================================
def clean_sql_for_sqlite(sql_text):
    # 백틱 제거 (MySQL 식별자 → SQLite 표준 식별자)
    sql_text = re.sub(r'`', '', sql_text)

    # 컬럼 수준 COMMENT 제거 (주석 안의 특수문자까지 포함)
    sql_text = re.sub(r"\s+COMMENT\s+'[^']*'", '', sql_text, flags=re.IGNORECASE)

    # 컬럼 수준 COLLATE 제거
    sql_text = re.sub(r"\s+COLLATE\s+'[^']*'", '', sql_text, flags=re.IGNORECASE)

    # AUTO_INCREMENT 제거 (SQLite는 INTEGER PRIMARY KEY가 자동 auto-increment)
    sql_text = re.sub(r'\s+AUTO_INCREMENT', '', sql_text, flags=re.IGNORECASE)

    # CREATE TABLE 내부의 INDEX / FULLTEXT INDEX 라인 제거 (라인별 처리)
    filtered_lines = []
    for line in sql_text.splitlines():
        if re.match(r'^\s*(FULLTEXT\s+)?INDEX\s+', line, re.IGNORECASE):
            continue
        filtered_lines.append(line)
    sql_text = '\n'.join(filtered_lines)

    # PRIMARY KEY의 USING BTREE/HASH 제거
    sql_text = re.sub(r'\s+USING\s+(BTREE|HASH)', '', sql_text, flags=re.IGNORECASE)

    # INT(n) → INTEGER (SQLite auto-increment은 INTEGER 타입 필요)
    sql_text = re.sub(r'\bINT\s*\(\d+\)', 'INTEGER', sql_text, flags=re.IGNORECASE)

    # DEFAULT '숫자' → DEFAULT 숫자 (따옴표 제거)
    sql_text = re.sub(r"DEFAULT\s+'(\d+\.?\d*)'", r'DEFAULT \1', sql_text, flags=re.IGNORECASE)

    # 테이블 수준 옵션 제거 (ENGINE=, ROW_FORMAT=, COLLATE=, COMMENT=)
    sql_text = re.sub(r'\bENGINE\s*=\s*\w+', '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r'\bROW_FORMAT\s*=\s*\w+', '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"COLLATE\s*=\s*'[^']*'", '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"COMMENT\s*=\s*'[^']*'", '', sql_text, flags=re.IGNORECASE)

    # INDEX 제거 후 생긴 닫는 괄호 직전의 trailing comma 정리
    sql_text = re.sub(r',(\s*\))', r'\1', sql_text)

    return sql_text

def execute_sql_file(cursor, filepath):
    print(f"⏳ 스테이징 중: {os.path.basename(filepath)} ...")
    with open(filepath, 'r', encoding='utf-8') as f:
        sql_script = f.read()
        sql_script = clean_sql_for_sqlite(sql_script)
        cursor.executescript(sql_script)

# ==========================================
# 3. 메인 마이그레이션 로직
# ==========================================
def main():
    if os.path.exists(STAGING_DB):
        os.remove(STAGING_DB)
        
    sqlite_conn = sqlite3.connect(STAGING_DB)
    sqlite_cursor = sqlite_conn.cursor()
    pg_engine = create_engine(PG_DB_URL)

    try:
        print("🚀 [STEP 1] SQL 파일을 임시 메모리에 적재하여 정제...")
        execute_sql_file(sqlite_cursor, SCHEMA_FILE)
        for sql_file in SQL_DATA_FILES:
            execute_sql_file(sqlite_cursor, sql_file)

        print("\n🚀 [STEP 2] 정제된 데이터를 PostgreSQL로 전송...")
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in sqlite_cursor.fetchall() if row[0] != 'sqlite_sequence']

        for table in tables:
            df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
            df.to_sql(table, con=pg_engine, if_exists='replace', index=False)
            print(f"  ✅ DB 이관 완료: '{table}' (총 {len(df)}행)")

        print("\n🚀 [STEP 3] 가격표 CSV 파일을 정제하여 PostgreSQL에 적재...")

        # 월별 이력 컬럼 매핑 (컬럼 15~38: [일반, 구독] × 12개월)
        MONTH_COLS = [
            ('2025-02', 15, 16), ('2025-03', 17, 18), ('2025-04', 19, 20),
            ('2025-05', 21, 22), ('2025-06', 23, 24), ('2025-07', 25, 26),
            ('2025-08', 27, 28), ('2025-09', 29, 30), ('2025-10', 31, 32),
            ('2025-11', 33, 34), ('2025-12', 35, 36), ('2026-02', 37, 38),
        ]
        all_price_items = []
        all_price_history = []

        for csv_file, source_type in [
            (CSV_DOMESTIC_FILE, '국산'),
            (CSV_IMPORTED_FILE, '수입'),
        ]:
            raw = pd.read_csv(csv_file, encoding='utf-8-sig', header=None, skiprows=3)
            raw.columns = range(len(raw.columns))

            for _, row in raw.iterrows():
                code = row.get(0)
                name = row.get(1)
                if pd.isna(code) or pd.isna(name):
                    continue

                item = {
                    'code': str(code).strip(),
                    'herb_name': str(name).strip(),
                    'origin': str(row.get(2, '')).strip() if pd.notna(row.get(2)) else None,
                    'grade': str(row.get(3, '')).strip() if pd.notna(row.get(3)) else None,
                    'source_type': source_type,
                    'price_per_geun': row.get(4) if pd.notna(row.get(4)) else None,
                    'packaging_unit_g': row.get(5) if pd.notna(row.get(5)) else None,
                    'packaging_unit_price': row.get(6) if pd.notna(row.get(6)) else None,
                    'box_quantity': row.get(7) if pd.notna(row.get(7)) else None,
                    'subscription_price': row.get(8) if pd.notna(row.get(8)) else None,
                    'subscription_unit_g': row.get(9) if pd.notna(row.get(9)) else None,
                    'subscription_unit_price': row.get(10) if pd.notna(row.get(10)) else None,
                    'subscription_box_qty': row.get(11) if pd.notna(row.get(11)) else None,
                    'manufacturer': str(row.get(12, '')).strip() if pd.notna(row.get(12)) else None,
                    'note': str(row.get(13, '')).strip() if pd.notna(row.get(13)) else None,
                    'discount_rate': str(row.get(14, '')).strip() if pd.notna(row.get(14)) else None,
                }
                all_price_items.append(item)

                # 월별 이력
                for year_month, reg_col, sub_col in MONTH_COLS:
                    reg_val = row.get(reg_col)
                    sub_val = row.get(sub_col)
                    if pd.notna(reg_val) or pd.notna(sub_val):
                        all_price_history.append({
                            'code': item['code'],
                            'herb_name': item['herb_name'],
                            'source_type': source_type,
                            'year_month': year_month,
                            'regular_price': reg_val if pd.notna(reg_val) else None,
                            'subscription_price': sub_val if pd.notna(sub_val) else None,
                        })

        df_items = pd.DataFrame(all_price_items)
        df_items.to_sql('price_item', con=pg_engine, if_exists='replace', index=False)
        print(f"  ✅ DB 이관 완료: 'price_item' (총 {len(df_items)}행)")

        df_history = pd.DataFrame(all_price_history)
        df_history.to_sql('price_history', con=pg_engine, if_exists='replace', index=False)
        print(f"  ✅ DB 이관 완료: 'price_history' (총 {len(df_history)}행)")

    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
    finally:
        sqlite_conn.close()
        pg_engine.dispose()
        if os.path.exists(STAGING_DB):
            os.remove(STAGING_DB)
        print("\n🎉 모든 데이터 마이그레이션 작업이 완료되었습니다!")

if __name__ == "__main__":
    main()