"""
Cache 관리 API — Redis 캐시 상태 조회, 수동 무효화
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_redis
from app.services.cache_service import (
    CACHE_PREFIX,
    get_herb_cache,
    invalidate_all_herb_cache,
    invalidate_herb_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])


class CacheStatsResponse(BaseModel):
    """캐시 통계 응답."""
    total_keys: int
    memory_used: str
    memory_max: str
    eviction_policy: str
    keyspace_hits: int
    keyspace_misses: int
    hit_rate: float


class InvalidateRequest(BaseModel):
    """캐시 무효화 요청."""
    herb_names: list[str] = Field(..., min_length=1, description="무효화할 약재명 목록")


# ── GET /cache/stats ─────────────────────────────────
@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """Redis 캐시 상태 및 히트율 조회."""
    redis = await get_redis()

    # herb:cache:* 키 수 카운트 (SCAN 기반)
    total_keys = 0
    cursor = "0"
    while cursor:
        cursor, keys = await redis.scan(cursor=cursor, match=f"{CACHE_PREFIX}*", count=500)
        total_keys += len(keys)
        if cursor == 0:
            break

    # INFO 명령으로 메모리/히트 통계
    info_memory = await redis.info("memory")
    info_stats = await redis.info("stats")

    memory_used = info_memory.get("used_memory_human", "N/A")
    memory_max = info_memory.get("maxmemory_human", "N/A")
    eviction_policy = info_memory.get("maxmemory_policy", "N/A")

    hits = info_stats.get("keyspace_hits", 0)
    misses = info_stats.get("keyspace_misses", 0)
    hit_rate = round(hits / (hits + misses) * 100, 2) if (hits + misses) > 0 else 0.0

    return CacheStatsResponse(
        total_keys=total_keys,
        memory_used=memory_used,
        memory_max=memory_max,
        eviction_policy=eviction_policy,
        keyspace_hits=hits,
        keyspace_misses=misses,
        hit_rate=hit_rate,
    )


# ── GET /cache/{herb_name} ───────────────────────────
@router.get("/{herb_name}")
async def get_cached_herb(herb_name: str):
    """특정 약재의 캐시 데이터 조회. Miss 시 DB fallback."""
    data = await get_herb_cache(herb_name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"'{herb_name}' 데이터를 찾을 수 없습니다.")
    return {"herb_name": herb_name, "data": data, "source": "cache_or_db"}


# ── DELETE /cache/{herb_name} ────────────────────────
@router.delete("/{herb_name}")
async def invalidate_single_herb(herb_name: str):
    """특정 약재 캐시 무효화. 다음 조회 시 DB 최신값으로 재적재."""
    deleted = await invalidate_herb_cache(herb_name)
    return {
        "herb_name": herb_name,
        "deleted": deleted,
        "message": f"'{herb_name}' 캐시 {'삭제됨' if deleted else '이미 없음'}",
    }


# ── DELETE /cache ────────────────────────────────────
@router.delete("")
async def invalidate_all():
    """herb:cache:* + herb:access:* 전체 캐시 무효화."""
    deleted = await invalidate_all_herb_cache()
    return {"deleted_count": deleted, "message": f"{deleted}개 캐시 키 전체 삭제됨"}
