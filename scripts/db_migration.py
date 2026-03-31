import sqlite3
import os
import re
import pandas as pd  # pylint: disable=import-error
from sqlalchemy import create_engine, text  # pylint: disable=import-error

# ==========================================
# 1. 파일 경로 및 DB 세팅
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

CSV_BASE_COLUMNS = ['코드', '약재명', '원산지', '구분', '근당 가격',
                     '포장 단위(g)', '포장 단위 당 가격', '박스 수량',
                     '구독 가격', '구독 포장 단위(g)', '구독 포장 단위 당 가격',
                     '구독 박스 수량', '제약사', '비고', '구독 구매 할인율']

PRICE_MONTHS = ['2월', '3월', '4월', '5월', '6월', '7월',
                '8월', '9월', '10월', '11월', '12월', '26년 2월']


# ==========================================
# 2. MySQL → SQLite 변환 함수
# ==========================================
def clean_sql_for_sqlite(sql_text):
    sql_text = re.sub(r'`', '', sql_text)
    sql_text = re.sub(r"\s+COMMENT\s+'[^']*'", '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"\s+COLLATE\s+'[^']*'", '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r'\s+AUTO_INCREMENT', '', sql_text, flags=re.IGNORECASE)

    filtered_lines = []
    for line in sql_text.splitlines():
        if re.match(r'^\s*(FULLTEXT\s+)?INDEX\s+', line, re.IGNORECASE):
            continue
        filtered_lines.append(line)
    sql_text = '\n'.join(filtered_lines)

    sql_text = re.sub(r'\s+USING\s+(BTREE|HASH)', '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r'\bINT\s*\(\d+\)', 'INTEGER', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"DEFAULT\s+'(\d+\.?\d*)'", r'DEFAULT \1', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r'\bENGINE\s*=\s*\w+', '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r'\bROW_FORMAT\s*=\s*\w+', '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"COLLATE\s*=\s*'[^']*'", '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"COMMENT\s*=\s*'[^']*'", '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r',(\s*\))', r'\1', sql_text)
    return sql_text


def execute_sql_file(cursor, filepath):
    print(f"  [..] 스테이징 중: {os.path.basename(filepath)} ...")
    with open(filepath, 'r', encoding='utf-8') as f:
        sql_script = f.read()
        sql_script = clean_sql_for_sqlite(sql_script)
        cursor.executescript(sql_script)


# ==========================================
# 3. CSV 전처리 함수
# ==========================================
def load_and_clean_csv(filepath, market_type):
    """CSV를 읽어 기본 정보(최신 가격) 테이블로 정리"""
    df = pd.read_csv(filepath, encoding='utf-8-sig', header=2)

    # 실제 헤더: 코드,약재명,원산지,구분,근당 가격,...  (15개 기본 + 월별 24개)
    # 중복 컬럼명 처리: pandas가 자동으로 .1, .2 등을 붙임
    cols = list(df.columns)

    # 기본 15개 컬럼에 명확한 이름 부여
    rename_map = {}
    for i, new_name in enumerate(CSV_BASE_COLUMNS):
        if i < len(cols):
            rename_map[cols[i]] = new_name
    df.rename(columns=rename_map, inplace=True)

    # 월별 가격 컬럼 이름 부여 (15번 이후 컬럼: 일반/구독 교대)
    remaining_cols = [c for c in df.columns if c not in CSV_BASE_COLUMNS]
    month_rename = {}
    for idx, col in enumerate(remaining_cols):
        month_idx = idx // 2
        price_type = '일반' if idx % 2 == 0 else '구독'
        if month_idx < len(PRICE_MONTHS):
            month_rename[col] = f"{PRICE_MONTHS[month_idx]}_{price_type}"
    df.rename(columns=month_rename, inplace=True)

    # 약재명 정리: 공백 제거, 줄바꿈 제거, 빈 행 제거
    df['약재명'] = df['약재명'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    df = df[df['약재명'].notna() & (df['약재명'] != '') & (df['약재명'] != 'nan')]

    # 원산지, 구분 정리
    df['원산지'] = df['원산지'].astype(str).str.strip().replace('nan', None)
    df['구분'] = df['구분'].astype(str).str.strip().replace('nan', None)
    df['제약사'] = df['제약사'].astype(str).str.strip().replace('nan', None)

    df['market_type'] = market_type
    return df


def extract_base_price_df(df):
    """CSV에서 기본 가격 정보만 추출 (최신 월 가격)"""
    base_cols = ['코드', '약재명', '원산지', '구분', '근당 가격',
                 '포장 단위(g)', '포장 단위 당 가격', '박스 수량',
                 '구독 가격', '구독 포장 단위(g)', '구독 포장 단위 당 가격',
                 '구독 박스 수량', '제약사', '비고', '구독 구매 할인율',
                 'market_type']
    existing = [c for c in base_cols if c in df.columns]
    return df[existing].copy()


# ==========================================
# 4. herb_unified 생성 함수
# ==========================================
def build_herb_unified(pg_engine, df_domestic, df_imported):
    """DB + CSV 양쪽에서 약재명을 수집해 herb_unified 테이블 생성"""

    # DB에서 약재명 수집
    db_herbs = pd.read_sql_query(
        "SELECT DISTINCT TRIM(md_title_kor) AS name_kor FROM han_medicine "
        "WHERE md_title_kor IS NOT NULL",
        pg_engine
    )
    db_herb_names = set(db_herbs['name_kor'].str.strip())

    # CSV에서 약재명 수집
    csv_domestic_names = set(df_domestic['약재명'].unique())
    csv_imported_names = set(df_imported['약재명'].unique())
    csv_herb_names = csv_domestic_names | csv_imported_names

    # 통합: source 구분
    all_names = db_herb_names | csv_herb_names
    rows = []
    for name in sorted(all_names):
        in_db = name in db_herb_names
        in_csv = name in csv_herb_names
        if in_db and in_csv:
            source = 'both'
        elif in_db:
            source = 'db_only'
        else:
            source = 'csv_only'
        rows.append({'name_kor': name, 'source': source})

    df_unified = pd.DataFrame(rows)

    # DB의 md_code 매핑 (약재명 → 대표 md_code, 첫 번째 것 사용)
    md_code_map = pd.read_sql_query(
        "SELECT TRIM(md_title_kor) AS name_kor, MIN(md_code) AS md_code "
        "FROM han_medicine WHERE md_title_kor IS NOT NULL "
        "GROUP BY TRIM(md_title_kor)",
        pg_engine
    )
    md_code_map['name_kor'] = md_code_map['name_kor'].str.strip()
    df_unified = df_unified.merge(md_code_map, on='name_kor', how='left')

    # PostgreSQL에 저장 (herb_id는 SERIAL로 자동 생성)
    with pg_engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS herb_unified CASCADE"))
        conn.execute(text("""
            CREATE TABLE herb_unified (
                herb_id SERIAL PRIMARY KEY,
                name_kor VARCHAR(100) UNIQUE NOT NULL,
                md_code VARCHAR(20),
                source VARCHAR(10) NOT NULL
            )
        """))
        conn.commit()

    df_unified[['name_kor', 'md_code', 'source']].to_sql(
        'herb_unified', con=pg_engine, if_exists='append', index=False
    )

    # herb_id 매핑 딕셔너리 반환
    herb_map = pd.read_sql_query(
        "SELECT herb_id, name_kor FROM herb_unified", pg_engine
    )
    return dict(zip(herb_map['name_kor'], herb_map['herb_id']))


# ==========================================
# 5. 메인 마이그레이션 로직
# ==========================================
def main():
    if os.path.exists(STAGING_DB):
        os.remove(STAGING_DB)

    sqlite_conn = sqlite3.connect(STAGING_DB)
    sqlite_cursor = sqlite_conn.cursor()
    pg_engine = create_engine(PG_DB_URL)

    try:
        # --- STEP 1: MySQL SQL → SQLite 스테이징 ---
        print(">> [STEP 1] SQL 파일을 임시 SQLite에 적재하여 정제...")
        execute_sql_file(sqlite_cursor, SCHEMA_FILE)
        for sql_file in SQL_DATA_FILES:
            execute_sql_file(sqlite_cursor, sql_file)

        # --- STEP 2: SQLite → PostgreSQL 전송 (기존 6개 테이블) ---
        print("\n>> [STEP 2] 정제된 데이터를 PostgreSQL로 전송...")
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in sqlite_cursor.fetchall() if r[0] != 'sqlite_sequence']

        for table in tables:
            df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
            df.to_sql(table, con=pg_engine, if_exists='replace', index=False)
            print(f"  [OK] '{table}' (총 {len(df)}행)")

        # --- STEP 3: CSV 전처리 ---
        print("\n>> [STEP 3] CSV 가격표 전처리...")
        df_domestic = load_and_clean_csv(CSV_DOMESTIC_FILE, 'domestic')
        df_imported = load_and_clean_csv(CSV_IMPORTED_FILE, 'imported')
        print(f"  [OK] 국산 가격표: {len(df_domestic)}행")
        print(f"  [OK] 수입 가격표: {len(df_imported)}행")

        # --- STEP 4: herb_unified 생성 ---
        print("\n>> [STEP 4] herb_unified (통합 약재 마스터) 생성...")
        herb_id_map = build_herb_unified(pg_engine, df_domestic, df_imported)
        print(f"  [OK] herb_unified: {len(herb_id_map)}개 약재")

        both = sum(1 for v in herb_id_map if True)  # count later
        with pg_engine.connect() as conn:
            stats = conn.execute(text(
                "SELECT source, COUNT(*) FROM herb_unified GROUP BY source ORDER BY source"
            )).fetchall()
        for source, cnt in stats:
            print(f"     - {source}: {cnt}개")

        # --- STEP 5: CSV에 herb_id FK 추가 후 PostgreSQL 적재 ---
        print("\n>> [STEP 5] CSV 가격표에 herb_id 연결 후 적재...")

        df_dom_base = extract_base_price_df(df_domestic)
        df_dom_base['herb_id'] = df_dom_base['약재명'].map(herb_id_map)
        df_dom_base.to_sql('price_domestic', con=pg_engine, if_exists='replace', index=False)
        matched = df_dom_base['herb_id'].notna().sum()
        print(f"  [OK] price_domestic: {len(df_dom_base)}행 (herb_id 연결: {matched}행)")

        df_imp_base = extract_base_price_df(df_imported)
        df_imp_base['herb_id'] = df_imp_base['약재명'].map(herb_id_map)
        df_imp_base.to_sql('price_imported', con=pg_engine, if_exists='replace', index=False)
        matched = df_imp_base['herb_id'].notna().sum()
        print(f"  [OK] price_imported: {len(df_imp_base)}행 (herb_id 연결: {matched}행)")

        # --- STEP 6: 기존 테이블에 herb_id 역참조 추가 ---
        print("\n>> [STEP 6] 기존 테이블에 herb_id 연결...")
        with pg_engine.connect() as conn:
            # han_medicine: md_title_kor로 직접 매칭
            conn.execute(text(
                "ALTER TABLE han_medicine ADD COLUMN IF NOT EXISTS herb_id INTEGER"
            ))
            conn.execute(text("""
                UPDATE han_medicine SET herb_id = h.herb_id
                FROM herb_unified h
                WHERE TRIM(han_medicine.md_title_kor) = h.name_kor
            """))
            conn.commit()
            r = conn.execute(text(
                "SELECT COUNT(*) FROM han_medicine WHERE herb_id IS NOT NULL"
            )).scalar()
            t = conn.execute(text("SELECT COUNT(*) FROM han_medicine")).scalar()
            print(f"  [OK] han_medicine: {r}/{t}행 herb_id 연결됨")

            # han_medicine_dj: mm_title_kor이 '약재명(원산지)' 형식이므로
            # 괄호 앞 이름 + 하이픈 앞 기본명으로 매칭 시도
            conn.execute(text(
                "ALTER TABLE han_medicine_dj ADD COLUMN IF NOT EXISTS herb_id INTEGER"
            ))
            conn.execute(text("""
                UPDATE han_medicine_dj SET herb_id = h.herb_id
                FROM herb_unified h
                WHERE h.name_kor = TRIM(
                    SPLIT_PART(SPLIT_PART(mm_title_kor, '(', 1), '-', 1)
                )
            """))
            conn.commit()
            r = conn.execute(text(
                "SELECT COUNT(*) FROM han_medicine_dj WHERE herb_id IS NOT NULL"
            )).scalar()
            t = conn.execute(text("SELECT COUNT(*) FROM han_medicine_dj")).scalar()
            print(f"  [OK] han_medicine_dj: {r}/{t}행 herb_id 연결됨")

        print("\n[DONE] 모든 마이그레이션 완료!")

    except Exception as e:
        print(f"\n[ERROR] 에러 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sqlite_conn.close()
        pg_engine.dispose()
        if os.path.exists(STAGING_DB):
            os.remove(STAGING_DB)


if __name__ == "__main__":
    main()
