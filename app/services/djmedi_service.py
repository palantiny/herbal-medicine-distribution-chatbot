"""
DJMEDI API 서비스 — 한약재 연동 API 클라이언트 (Redis 캐싱 포함)

API 엔드포인트: https://devapi.djmedi.net/djherb/

지원 API:
  - herbmaker      : 전체 제조사 목록 (mk_code, mk_name)
  - herbmedicine   : 제조사별 약재 목록 (md_code, md_medi, md_name)
  - membermedicine : 업체(cfcode)별 사용 가능 약재 (mm_name, mm_origin, mk_name)

모든 약재 데이터는 이 API를 통해서만 가져옵니다.
로컬 PostgreSQL에는 users 테이블과 향후 추가될 CSV 테이블만 존재합니다.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.database import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()

# ── 캐시 키 / TTL ─────────────────────────────────────────────────────────────
_MAKER_CACHE_KEY = "djmedi:herbmaker"
_MEDICINE_CACHE_PREFIX = "djmedi:herbmedicine:"   # + mk_code
_MEMBER_CACHE_PREFIX = "djmedi:membermedicine:"   # + cfcode:md_medi

_MAKER_TTL = 86400    # 제조사 목록: 24시간
_MEDICINE_TTL = 3600  # 약재 목록: 1시간
_MEMBER_TTL = 1800    # 업체별 약재: 30분


# ── 내부 HTTP 헬퍼 ────────────────────────────────────────────────────────────
async def _get(params: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            settings.DJMEDI_API_BASE_URL,
            params=params,
            headers={"cfauthkey": settings.DJMEDI_AUTH_KEY},
        )
        response.raise_for_status()
        return response.json()


def _validate_response(data: dict[str, Any]) -> list[dict]:
    code = str(data.get("resultCode", ""))
    if code == "204":
        return []
    if code != "200":
        logger.warning("DJMEDI API non-200: code=%s msg=%s", code, data.get("resultMessage"))
        return []
    return data.get("list") or []


# ── Redis 캐시 헬퍼 ───────────────────────────────────────────────────────────
async def _cache_get(key: str) -> list[dict] | None:
    try:
        redis = await get_redis()
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning("DJMEDI cache GET error (%s): %s", key, e)
    return None


async def _cache_set(key: str, data: list[dict], ttl: int) -> None:
    try:
        redis = await get_redis()
        await redis.set(key, json.dumps(data, ensure_ascii=False), ex=ttl)
    except Exception as e:
        logger.warning("DJMEDI cache SET error (%s): %s", key, e)


# ── 기본 API 함수 ─────────────────────────────────────────────────────────────

async def get_maker_list(language: str = "kor") -> list[dict]:
    """전체 제조사 목록 (herbmaker). 24시간 캐시."""
    cached = await _cache_get(_MAKER_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        data = await _get({"apiCode": "herbmaker", "language": language})
        result = _validate_response(data)
        await _cache_set(_MAKER_CACHE_KEY, result, _MAKER_TTL)
        logger.info("DJMEDI herbmaker: %d makers fetched", len(result))
        return result
    except Exception as e:
        logger.exception("DJMEDI herbmaker error: %s", e)
        return []


async def get_medicine_by_maker(mk_code: str, language: str = "kor") -> list[dict]:
    """제조사별 약재 목록 (herbmedicine). 1시간 캐시."""
    cache_key = f"{_MEDICINE_CACHE_PREFIX}{mk_code}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = await _get({"apiCode": "herbmedicine", "language": language, "search": mk_code})
        result = _validate_response(data)
        await _cache_set(cache_key, result, _MEDICINE_TTL)
        logger.info("DJMEDI herbmedicine: mk_code=%s → %d items", mk_code, len(result))
        return result
    except Exception as e:
        logger.exception("DJMEDI herbmedicine error: mk_code=%s %s", mk_code, e)
        return []


async def get_member_medicine(cfcode: str, md_medi: str, language: str = "kor") -> list[dict]:
    """업체별 사용 약재 (membermedicine). 30분 캐시."""
    cache_key = f"{_MEMBER_CACHE_PREFIX}{cfcode}:{md_medi}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = await _get({
            "apiCode": "membermedicine",
            "language": language,
            "search": md_medi,
            "cfcode": cfcode,
        })
        result = _validate_response(data)
        await _cache_set(cache_key, result, _MEMBER_TTL)
        logger.info("DJMEDI membermedicine: cfcode=%s md_medi=%s → %d items", cfcode, md_medi, len(result))
        return result
    except Exception as e:
        logger.exception("DJMEDI membermedicine error: cfcode=%s md_medi=%s %s", cfcode, md_medi, e)
        return []


# ── 룩업 헬퍼 ────────────────────────────────────────────────────────────────

_CORP_SUFFIX_RE = __import__("re").compile(
    r"[(（]?주[)）]|주식회사|농업회사법인|영농조합법인\s*|협동조합|\s*(주)\s*"
)


def _normalize_corp_name(name: str) -> str:
    """
    제조사명에서 법인 표기(주식회사, (주), 농업회사법인 등)를 제거해 핵심 상호만 추출.
    예: '씨케이주식회사' → '씨케이', '(주)허브팜' → '허브팜'
    """
    return _CORP_SUFFIX_RE.sub("", name).strip()


async def find_mk_code_by_name(maker_name: str) -> str | None:
    """
    정규화된 제조사명으로 mk_code를 찾아 반환.
    법인 표기를 제거한 핵심 상호끼리 비교해 '씨케이(주)' ↔ '씨케이주식회사' 매칭.
    herbmaker 캐시(24h)에서 검색 — 추가 API 호출 없음.
    """
    makers = await get_maker_list()
    query_core = _normalize_corp_name(maker_name).lower()
    if not query_core:
        logger.warning("mk_code 검색 실패: 정규화 후 빈 문자열 (원본: '%s')", maker_name)
        return None

    for m in makers:
        mk_name = m.get("mk_name", "")
        mk_core = _normalize_corp_name(mk_name).lower()
        if query_core in mk_core or mk_core in query_core:
            logger.info("mk_code 찾음: '%s' → %s ('%s')", maker_name, m["mk_code"], mk_name)
            return m["mk_code"]

    logger.warning("mk_code 없음: '%s' (정규화: '%s')", maker_name, query_core)
    return None


async def find_md_medi_by_herb_name(herb_name: str) -> list[str]:
    """
    약재명으로 md_medi(주성분코드) 목록을 반환.
    전체 제조사의 herbmedicine을 병렬로 조회해 herb_name으로 필터링.
    결과는 herbmedicine 캐시(1h)를 최대한 활용.
    """
    makers = await get_maker_list()
    if not makers:
        return []

    # 모든 제조사의 약재 목록 병렬 조회 (캐시 히트 시 매우 빠름)
    tasks = [get_medicine_by_maker(m["mk_code"]) for m in makers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    md_medi_set: set[str] = set()
    for result in results:
        if isinstance(result, list):
            for item in result:
                if herb_name in item.get("md_name", ""):
                    md_medi = item.get("md_medi", "")
                    if md_medi:
                        md_medi_set.add(md_medi)

    logger.info("'%s' md_medi 발견: %s", herb_name, list(md_medi_set))
    return list(md_medi_set)


# ── 스마트 검색 오케스트레이터 ────────────────────────────────────────────────

async def smart_search(
    intent: str,
    maker_name: str | None = None,
    herb_name: str | None = None,
    origin: str | None = None,
    cfcode: str | None = None,
) -> tuple[str, list[dict]]:
    """
    intent에 따라 적절한 DJMEDI API를 호출하고 결과를 반환.

    Returns: (api_code_for_format, items)

    intent 목록:
      get_maker_list    : 전체 제조사 목록
      get_herb_by_maker : 특정 제조사의 약재 목록 (maker_name 필수)
      get_herb_by_name  : 약재명으로 전체 검색 (herb_name 필수)
      get_my_medicines  : 내 업체(cfcode) 기준 특정 약재 조회 (herb_name + cfcode 필수)
    """
    # ── 1. 전체 제조사 목록 ─────────────────────────────────────────────────
    if intent == "get_maker_list":
        items = await get_maker_list()
        return "herbmaker", items

    # ── 2. 특정 제조사 약재 목록 ────────────────────────────────────────────
    if intent == "get_herb_by_maker":
        if not maker_name:
            logger.warning("get_herb_by_maker: maker_name 없음")
            return "herbmedicine", []

        mk_code = await find_mk_code_by_name(maker_name)
        if not mk_code:
            return "herbmedicine", []

        items = await get_medicine_by_maker(mk_code)

        # herb_name 필터 (있는 경우)
        if herb_name:
            items = [i for i in items if herb_name in (i.get("md_name") or "")]

        # origin 필터 불가 안내 — herbmedicine API 응답에 원산지 정보가 없음
        # 원산지 정보가 필요하면 membermedicine(get_my_medicines) 경로 사용 필요
        if origin:
            items = [{"_notice": f"[안내] DJMEDI herbmedicine API는 원산지 정보를 제공하지 않아 '{origin}' 필터를 적용할 수 없습니다. 업체(cfcode) 기준 원산지별 조회가 필요하시면 '내 업체 기준으로 {origin} 약재 보여줘'라고 질문해 주세요.", "_type": "notice"}] + items

        return "herbmedicine", items

    # ── 3. 약재명으로 전체 검색 ─────────────────────────────────────────────
    if intent == "get_herb_by_name":
        if not herb_name:
            logger.warning("get_herb_by_name: herb_name 없음")
            return "herbmedicine", []

        makers = await get_maker_list()
        tasks = [get_medicine_by_maker(m["mk_code"]) for m in makers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[dict] = []
        for result in results:
            if isinstance(result, list):
                filtered = [i for i in result if herb_name and herb_name in (i.get("md_name") or "")]
                items.extend(filtered)

        # 중복 제거 (md_code 기준)
        seen: set[str] = set()
        unique: list[dict] = []
        for item in items:
            key = item.get("md_code", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(item)

        return "herbmedicine", unique

    # ── 4. 내 업체 기준 약재 조회 (membermedicine) ───────────────────────────
    if intent == "get_my_medicines":
        if not cfcode:
            logger.warning("get_my_medicines: cfcode 없음")
            return "membermedicine", []
        if not herb_name:
            logger.warning("get_my_medicines: herb_name 없음")
            return "membermedicine", []

        # 약재명 → md_medi 코드 목록 (API 병렬 조회)
        md_medi_list = await find_md_medi_by_herb_name(herb_name)
        if not md_medi_list:
            logger.info("'%s'의 md_medi 없음 → membermedicine 스킵", herb_name)
            return "membermedicine", []

        # md_medi별 membermedicine 병렬 조회
        tasks = [get_member_medicine(cfcode, md_medi) for md_medi in md_medi_list[:10]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items = []
        for result in results:
            if isinstance(result, list):
                items.extend(result)

        # origin 필터 (있는 경우)
        if origin:
            items = [i for i in items if origin in i.get("mm_origin", "")]

        return "membermedicine", items

    logger.warning("알 수 없는 intent: %s", intent)
    return "unknown", []


# ── 결과 포맷터 ───────────────────────────────────────────────────────────────

def format_djmedi_result(api_code: str, items: list[dict]) -> str:
    """DJMEDI API 결과를 LLM3 프롬프트 삽입용 텍스트로 변환."""
    # notice 아이템 분리 (_type=notice는 데이터 행이 아님)
    notices = [i["_notice"] for i in items if i.get("_type") == "notice"]
    data_items = [i for i in items if i.get("_type") != "notice"]

    if not data_items:
        base = f"[DJMEDI {api_code}] 조회 결과 없음"
        return "\n".join(notices + [base]) if notices else base

    lines = [f"[DJMEDI {api_code} 조회 결과 — {len(data_items)}건]"]
    for item in data_items:
        if api_code == "herbmaker":
            lines.append(f"  mk_code={item.get('mk_code')} / 제조사명={item.get('mk_name')}")
        elif api_code == "herbmedicine":
            lines.append(
                f"  md_code={item.get('md_code')} / 약재명={item.get('md_name')} "
                f"/ 주성분코드={item.get('md_medi')} / 제조사={item.get('mk_name')}"
            )
        elif api_code == "membermedicine":
            lines.append(
                f"  약재명={item.get('mm_name')} / 원산지={item.get('mm_origin')} "
                f"/ 제조사={item.get('mk_name')} / 주성분코드={item.get('md_medi')}"
            )
        else:
            lines.append(f"  {item}")

    result = "\n".join(lines)
    if notices:
        result = "\n".join(notices) + "\n\n" + result
    return result
