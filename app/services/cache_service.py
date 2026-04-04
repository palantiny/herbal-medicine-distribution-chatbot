"""
Redis 스마트 캐싱 서비스
- Frequency-Based Caching: 2회 이상 참조된 약재만 캐시 적재
- Dynamic Caching: Cache Miss 시 DB 조회, 접근 횟수 충족 시 TTL(1h) 부여 적재
- Cache Invalidation: 원본 데이터 변경 시 해당 키 + 접근 카운터 삭제
"""
import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text

from app.core.database import async_session_maker, get_redis

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────
CACHE_PREFIX = "herb:cache:"
ACCESS_COUNT_PREFIX = "herb:access:"
DYNAMIC_TTL = 3600  # 동적 캐시 TTL: 1시간
ACCESS_COUNT_TTL = 86400  # 접근 카운터 TTL: 24시간
CACHE_THRESHOLD = 2  # 이 횟수 이상 접근 시 캐시 적재


# ── 내부 유틸 ─────────────────────────────────────────
def _cache_key(herb_name: str) -> str:
    return f"{CACHE_PREFIX}{herb_name}"


def _access_key(herb_name: str) -> str:
    return f"{ACCESS_COUNT_PREFIX}{herb_name}"


def _serialize(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _deserialize(raw: str) -> dict | list:
    return json.loads(raw)


# ── 1) Cache Get (Frequency-Based Dynamic Caching) ───
async def get_herb_cache(herb_name: str) -> dict | None:
    """
    캐시 조회.
    - Hit → 파싱 후 반환.
    - Miss → DB 조회 + 접근 횟수 증가. 2회 이상이면 캐시 적재(TTL 1h).
    - DB에도 없으면 None.
    """
    redis = await get_redis()
    key = _cache_key(herb_name)

    # Cache Hit
    raw = await redis.get(key)
    if raw is not None:
        logger.info("Cache HIT: %s", herb_name)
        return _deserialize(raw)

    # Cache Miss → DB 조회
    logger.info("Cache MISS: %s → DB fallback", herb_name)
    data = await _fetch_herb_from_db(herb_name)
    if data is None:
        return None

    # 접근 횟수 증가 (24시간 TTL 카운터)
    access_key = _access_key(herb_name)
    count = await redis.incr(access_key)
    if count == 1:
        await redis.expire(access_key, ACCESS_COUNT_TTL)

    # 2회 이상 접근 시에만 캐시 적재
    if count >= CACHE_THRESHOLD:
        await redis.set(key, _serialize(data), ex=DYNAMIC_TTL)
        logger.info("Cache SET (access=%d): %s (TTL=%ds)", count, herb_name, DYNAMIC_TTL)
    else:
        logger.info("Cache SKIP (access=%d/%d): %s", count, CACHE_THRESHOLD, herb_name)

    return data


async def set_herb_cache(herb_name: str, data: dict, ttl: int = DYNAMIC_TTL) -> None:
    """명시적 캐시 설정. 접근 카운터와 무관하게 강제 적재."""
    redis = await get_redis()
    key = _cache_key(herb_name)
    await redis.set(key, _serialize(data), ex=ttl)


async def get_herbs_bulk(herb_names: list[str]) -> dict[str, dict | None]:
    """여러 약재를 한 번에 조회. MGET으로 네트워크 왕복 최소화."""
    redis = await get_redis()
    keys = [_cache_key(name) for name in herb_names]
    raw_values = await redis.mget(keys)

    result: dict[str, dict | None] = {}
    miss_names: list[str] = []

    for name, raw in zip(herb_names, raw_values):
        if raw is not None:
            result[name] = _deserialize(raw)
        else:
            result[name] = None
            miss_names.append(name)

    # Cache Miss 건은 get_herb_cache를 통해 접근 카운터 반영
    for name in miss_names:
        data = await get_herb_cache(name)
        result[name] = data

    return result


# ── 2) Cache Invalidation ────────────────────────────
async def invalidate_herb_cache(herb_name: str) -> bool:
    """캐시 + 접근 카운터 삭제."""
    redis = await get_redis()
    key = _cache_key(herb_name)
    access_key = _access_key(herb_name)
    deleted = await redis.delete(key, access_key)
    if deleted:
        logger.info("Cache INVALIDATED: %s", herb_name)
    return bool(deleted)


async def invalidate_herbs_bulk(herb_names: list[str]) -> int:
    """여러 약재 캐시 + 접근 카운터 일괄 무효화."""
    if not herb_names:
        return 0
    redis = await get_redis()
    keys = []
    for name in herb_names:
        keys.append(_cache_key(name))
        keys.append(_access_key(name))
    deleted = await redis.delete(*keys)
    logger.info("Cache INVALIDATED (bulk): %d keys", deleted)
    return deleted


async def invalidate_all_herb_cache() -> int:
    """herb:cache:* + herb:access:* 전체 삭제."""
    redis = await get_redis()
    total_deleted = 0
    for pattern in (f"{CACHE_PREFIX}*", f"{ACCESS_COUNT_PREFIX}*"):
        cursor = "0"
        while cursor:
            cursor, keys = await redis.scan(
                cursor=cursor, match=pattern, count=200,
            )
            if keys:
                total_deleted += await redis.delete(*keys)
            if cursor == 0:
                break
    logger.info("Cache INVALIDATED (all): %d keys", total_deleted)
    return total_deleted


# ── 내부: DB Fallback 조회 ───────────────────────────
async def _fetch_herb_from_db(herb_name: str) -> dict | None:
    """
    DB에서 약재 관련 전체 정보를 조회하여 캐시 value 형태의 dict로 반환.
    - han_medicine: 약재 마스터 (효능, 원산지, 설명, 가격 등)
    - han_medicine_dj: 시설별 약재 상세 (성미, 귀경, 가격)
    - price_item: 가격표 (국산/수입)
    - price_history: 월별 가격 이력
    - han_warehouse: 재고 입출고 이력
    """
    async with async_session_maker() as session:
        # han_medicine — 약재 마스터
        med_result = await session.execute(text("""
            SELECT md_seq, md_code, md_title_kor, md_title_chn, md_title_eng,
                   md_origin_kor, md_desc_kor, md_feature_kor, md_note_kor,
                   md_interact_kor, md_relate_kor, md_property_kor,
                   md_price, md_qty, md_status
            FROM han_medicine
            WHERE md_title_kor LIKE :pattern
        """), {"pattern": f"%{herb_name}%"})
        med_rows = med_result.fetchall()

        # han_medicine_dj — 시설별 약재 상세
        dj_result = await session.execute(text("""
            SELECT mm_title_kor, mm_origin_kor, mm_state, mm_taste, mm_object,
                   mm_feature, mm_alias, mm_desc, mm_caution,
                   mm_price, mm_qty, mm_status
            FROM han_medicine_dj
            WHERE mm_title_kor LIKE :pattern
        """), {"pattern": f"%{herb_name}%"})
        dj_rows = dj_result.fetchall()

        # price_item — 가격표
        price_result = await session.execute(text("""
            SELECT code, herb_name, origin, grade, source_type,
                   price_per_geun, packaging_unit_g, packaging_unit_price,
                   box_quantity, subscription_price, manufacturer, note
            FROM price_item
            WHERE herb_name LIKE :pattern
        """), {"pattern": f"%{herb_name}%"})
        price_rows = price_result.fetchall()

        # price_history — 월별 가격 이력
        history_result = await session.execute(text("""
            SELECT code, herb_name, source_type, year_month,
                   regular_price, subscription_price
            FROM price_history
            WHERE herb_name LIKE :pattern
            ORDER BY year_month DESC
        """), {"pattern": f"%{herb_name}%"})
        history_rows = history_result.fetchall()

        # han_warehouse — 재고/입출고
        wh_result = await session.execute(text("""
            SELECT wh_title, wh_type, wh_qty, wh_remain, wh_price,
                   wh_origin, wh_maker, wh_date, wh_status
            FROM han_warehouse
            WHERE wh_title LIKE :pattern
        """), {"pattern": f"%{herb_name}%"})
        wh_rows = wh_result.fetchall()

    if not med_rows and not dj_rows and not price_rows and not wh_rows:
        return None

    data: dict[str, Any] = {
        "herb_name": herb_name,
        "medicine": [],
        "medicine_dj": [],
        "price_items": [],
        "price_history": [],
        "warehouse": [],
    }

    for row in med_rows:
        data["medicine"].append({
            "md_seq": row[0], "md_code": row[1],
            "name_kor": row[2], "name_chn": row[3], "name_eng": row[4],
            "origin": row[5], "description": row[6],
            "feature": row[7], "note": row[8],
            "interaction": row[9], "related": row[10], "property": row[11],
            "price": float(row[12]) if row[12] else None,
            "stock_qty": row[13], "status": row[14],
        })

    for row in dj_rows:
        data["medicine_dj"].append({
            "name_kor": row[0], "origin": row[1],
            "nature": row[2], "taste": row[3], "meridian": row[4],
            "feature": row[5], "alias": row[6],
            "description": row[7], "caution": row[8],
            "price": float(row[9]) if row[9] else None,
            "stock_qty": row[10], "status": row[11],
        })

    for row in price_rows:
        data["price_items"].append({
            "code": row[0], "herb_name": row[1], "origin": row[2],
            "grade": row[3], "source_type": row[4],
            "price_per_geun": row[5],
            "packaging_unit_g": row[6], "packaging_unit_price": row[7],
            "box_quantity": row[8], "subscription_price": row[9],
            "manufacturer": row[10], "note": row[11],
        })

    for row in history_rows:
        data["price_history"].append({
            "code": row[0], "herb_name": row[1], "source_type": row[2],
            "year_month": row[3],
            "regular_price": row[4], "subscription_price": row[5],
        })

    for row in wh_rows:
        data["warehouse"].append({
            "title": row[0], "type": row[1],
            "qty": row[2], "remain": row[3],
            "price": float(row[4]) if row[4] else None,
            "origin": row[5], "maker": row[6],
            "date": row[7], "status": row[8],
        })

    return data
