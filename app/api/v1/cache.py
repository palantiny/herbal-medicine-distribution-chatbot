"""
Cache 관리 API — DJMEDI Redis 캐시 상태 조회 및 수동 무효화
"""
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.database import get_redis
from app.services.djmedi_service import (
    _MAKER_CACHE_KEY,
    _MEDICINE_CACHE_PREFIX,
    _MEMBER_CACHE_PREFIX,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cache", tags=["cache"])


class CacheStatsResponse(BaseModel):
    djmedi_keys: int
    memory_used: str
    keyspace_hits: int
    keyspace_misses: int
    hit_rate: float


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """DJMEDI 캐시 키 수 및 Redis 히트율 조회."""
    redis = await get_redis()

    total_keys = 0
    for pattern in (f"{_MEDICINE_CACHE_PREFIX}*", f"{_MEMBER_CACHE_PREFIX}*", _MAKER_CACHE_KEY):
        cursor: Any = "0"
        while cursor:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=500)
            total_keys += len(keys)
            if cursor == 0:
                break

    info_memory = await redis.info("memory")
    info_stats = await redis.info("stats")
    hits = info_stats.get("keyspace_hits", 0)
    misses = info_stats.get("keyspace_misses", 0)
    hit_rate = round(hits / (hits + misses) * 100, 2) if (hits + misses) > 0 else 0.0

    return CacheStatsResponse(
        djmedi_keys=total_keys,
        memory_used=info_memory.get("used_memory_human", "N/A"),
        keyspace_hits=hits,
        keyspace_misses=misses,
        hit_rate=hit_rate,
    )


@router.delete("/makers")
async def invalidate_maker_cache():
    """herbmaker 캐시 삭제 (다음 조회 시 DJMEDI API 재호출)."""
    redis = await get_redis()
    deleted = await redis.delete(_MAKER_CACHE_KEY)
    return {"deleted": bool(deleted), "key": _MAKER_CACHE_KEY}


@router.delete("/medicines")
async def invalidate_medicine_cache():
    """herbmedicine 전체 캐시 삭제."""
    redis = await get_redis()
    total = 0
    cursor: Any = "0"
    while cursor:
        cursor, keys = await redis.scan(cursor=cursor, match=f"{_MEDICINE_CACHE_PREFIX}*", count=500)
        if keys:
            total += await redis.delete(*keys)
        if cursor == 0:
            break
    return {"deleted_count": total}


@router.delete("/members")
async def invalidate_member_cache():
    """membermedicine 전체 캐시 삭제."""
    redis = await get_redis()
    total = 0
    cursor: Any = "0"
    while cursor:
        cursor, keys = await redis.scan(cursor=cursor, match=f"{_MEMBER_CACHE_PREFIX}*", count=500)
        if keys:
            total += await redis.delete(*keys)
        if cursor == 0:
            break
    return {"deleted_count": total}


@router.delete("")
async def invalidate_all_djmedi_cache():
    """DJMEDI 캐시 전체 삭제."""
    redis = await get_redis()
    total = 0
    patterns = [_MAKER_CACHE_KEY, f"{_MEDICINE_CACHE_PREFIX}*", f"{_MEMBER_CACHE_PREFIX}*"]
    for pattern in patterns:
        cursor: Any = "0"
        while cursor:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                total += await redis.delete(*keys)
            if cursor == 0:
                break
    return {"deleted_count": total, "message": f"DJMEDI 캐시 {total}개 삭제됨"}
