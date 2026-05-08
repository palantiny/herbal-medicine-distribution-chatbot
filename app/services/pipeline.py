"""
LLM 파이프라인 — 순차 실행

흐름:
  LLM1 엔티티 추출 → BM25 스킴 리졸버 → LLM2 라우팅
      ├─ KNOWLEDGE_FIRST → 모노그래프 prefetch → LLM3 → 사후 herb_card 부착
      ├─ DB_FIRST        → DJMEDI API 호출 → LLM3
      └─ SQL             → SQL 실행 → LLM3
"""
from __future__ import annotations

import json
import logging
from typing import Literal
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.djmedi_service import format_djmedi_result, smart_search
from app.services.entity_extractor import extract_entities
from app.services.herb_mention_extractor import extract_mentioned_herbs
from app.services.monograph_service import format_many_for_prompt, lookup_for_herbs
from app.services.scheme_resolver import SqlHint, format_hints_for_prompt, resolve_entities
from app.services.sql_worker import SQL_RESULT_PREFIX, SQL_TASK_QUEUE
from app.utils.prompts import (
    LLM2_SYSTEM_PROMPT,
    LLM2_USER_TEMPLATE,
    LLM3_SYSTEM_PROMPT,
    LLM3_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ── OpenAI 클라이언트 싱글톤 ──────────────────────────────────────────────────
_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


_STREAM_CHUNK_SIZE = 4


# ── LLM2 구조화 출력 스키마 ───────────────────────────────────────────────────
class DjmediQuerySpec(BaseModel):
    intent: Literal[
        "get_maker_list",
        "get_herb_by_maker",
        "get_herb_by_name",
        "get_my_medicines",
    ] = Field(description="조회 의도")
    maker_name: str | None = Field(default=None, description="정규화된 제조사명")
    herb_name: str | None = Field(default=None, description="정규화된 약재명")
    origin: str | None = Field(default=None, description="원산지 필터")


class Llm2Output(BaseModel):
    mode: Literal["KNOWLEDGE_FIRST", "DB_FIRST", "SQL"] = Field(description="처리 방식")
    sql: str | None = Field(default=None, description="mode=SQL일 때 SELECT 쿼리")
    djmedi_query: DjmediQuerySpec | None = Field(
        default=None, description="mode=DB_FIRST일 때 DJMEDI 조회 스펙"
    )
    reason: str = Field(description="mode 선택 이유 (내부 로깅용)")


# ── 유틸 ─────────────────────────────────────────────────────────────────────
async def _stream_text(redis: Redis, channel: str, text: str) -> None:
    for i in range(0, len(text), _STREAM_CHUNK_SIZE):
        await redis.publish(
            channel,
            json.dumps({"type": "token", "content": text[i:i + _STREAM_CHUNK_SIZE]}, ensure_ascii=False),
        )


async def _publish_status(redis: Redis, channel: str, message: str) -> None:
    await redis.publish(channel, json.dumps({"type": "status", "content": message}, ensure_ascii=False))


async def _call_llm_stream(system_prompt: str, user_content: str, redis: Redis, channel: str) -> str:
    full = ""
    try:
        stream = await _get_client().chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            stream=True,
            temperature=0.2,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full += token
                await redis.publish(channel, json.dumps({"type": "token", "content": token}, ensure_ascii=False))
        return full
    except Exception as e:
        logger.exception("LLM stream error: %s", e)
        msg = "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        await _stream_text(redis, channel, msg)
        return msg


async def _execute_sql_via_redis(sql: str, redis: Redis) -> str:
    if not sql or not sql.strip().upper().startswith("SELECT"):
        return "SELECT 쿼리만 실행 가능합니다."
    task_id = str(uuid4())
    result_key = f"{SQL_RESULT_PREFIX}{task_id}"
    await redis.lpush(SQL_TASK_QUEUE, json.dumps({"task_id": task_id, "sql": sql, "result_key": result_key}, ensure_ascii=False))
    result = await redis.blpop(result_key, timeout=30)
    if result is None:
        return "DB 조회 시간이 초과되었습니다."
    _, data_str = result
    data = json.loads(data_str)
    if isinstance(data, dict) and "error" in data:
        return f"DB 조회 오류: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


# ── 파이프라인 단계 함수 ──────────────────────────────────────────────────────

async def _step_llm1(question: str, chat_history: str, redis: Redis, channel: str):
    await _publish_status(redis, channel, "질문 분석 중...")
    return await extract_entities(question, chat_history)


def _step_bm25(extraction) -> SqlHint:
    if extraction and extraction.entities:
        return resolve_entities(extraction.entities)
    return SqlHint()


async def _step_llm2(question: str, chat_history: str, extraction, hint: SqlHint, cfcode: str | None) -> Llm2Output:
    needs_db_hint = extraction.needs_db if extraction else True
    hints_text = format_hints_for_prompt(hint)
    user_content = LLM2_USER_TEMPLATE.format(
        chat_history=chat_history,
        needs_db="예" if needs_db_hint else "아니오 (LLM1이 일반 대화로 판정함)",
        sql_hints=hints_text,
        question=question,
    )

    try:
        response = await _get_client().beta.chat.completions.parse(
            model="gpt-4o",
            messages=[{"role": "system", "content": LLM2_SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
            response_format=Llm2Output,
            temperature=0.1,
        )
        parsed: Llm2Output | None = response.choices[0].message.parsed
    except Exception as e:
        logger.exception("LLM2 route error: %s", e)
        parsed = None

    if parsed is None:
        logger.warning("LLM2 파싱 실패 → KNOWLEDGE_FIRST fallback")
        return Llm2Output(mode="KNOWLEDGE_FIRST", reason="LLM2 파싱 실패 fallback")

    logger.info("LLM2: mode=%s reason=%.100s", parsed.mode, parsed.reason or "")
    return parsed


async def _step_execute(parsed: Llm2Output, cfcode: str | None, redis: Redis, channel: str) -> str:
    """DB_FIRST/SQL 모드에서만 호출. KNOWLEDGE_FIRST는 호출하지 않는다."""
    if parsed.mode == "SQL":
        if not parsed.sql:
            logger.warning("LLM2: mode=SQL이지만 sql=None")
            return ""
        await _publish_status(redis, channel, "DB 조회 중...")
        sql = parsed.sql.replace("{cfcode}", cfcode or "").replace("{{cfcode}}", cfcode or "")
        return await _execute_sql_via_redis(sql, redis)

    if parsed.mode == "DB_FIRST":
        await _publish_status(redis, channel, "약재 데이터 조회 중...")
        spec = parsed.djmedi_query or DjmediQuerySpec(intent="get_maker_list")
        try:
            api_code, items = await smart_search(
                intent=spec.intent,
                maker_name=spec.maker_name,
                herb_name=spec.herb_name,
                origin=spec.origin,
                cfcode=cfcode,
            )
            return format_djmedi_result(api_code, items)
        except Exception as e:
            logger.exception("DJMEDI execute error: %s", e)
            return "외부 약재 데이터 조회에 실패했습니다."

    return ""


def _step_prefetch_monograph(parsed: Llm2Output, hint: SqlHint) -> str:
    """KNOWLEDGE_FIRST에서 SqlHint로 정규화된 herb_name이 있으면 모노그래프 블록 반환."""
    if parsed.mode != "KNOWLEDGE_FIRST":
        return ""
    herb_names: list[str] = []
    for h in hint.hints:
        if h.slot in ("herb_name", "herb", "herbs"):
            herb_names.append(h.value)
    if not herb_names:
        return ""
    monos = lookup_for_herbs(herb_names)
    return format_many_for_prompt(monos)


async def _step_llm3(
    parsed: Llm2Output,
    data_result: str,
    monograph_block: str,
    question: str,
    chat_history: str,
    redis: Redis,
    channel: str,
) -> str:
    user_content = LLM3_USER_TEMPLATE.format(
        data_result=data_result or "(조회 결과 없음)",
        monograph_block=monograph_block or "(없음)",
        chat_history=chat_history,
        question=question,
    )
    return await _call_llm_stream(LLM3_SYSTEM_PROMPT, user_content, redis, channel)


async def _step_post_cards(
    parsed: Llm2Output,
    answer_text: str,
    cfcode: str | None,
    redis: Redis,
    channel: str,
) -> None:
    """KNOWLEDGE_FIRST에서 답변 종료 후 멘션된 약재를 DJMEDI에서 조회해 herb_card 이벤트 발행."""
    if parsed.mode != "KNOWLEDGE_FIRST":
        return
    if not answer_text or not answer_text.strip():
        return
    herbs = await extract_mentioned_herbs(answer_text)
    if not herbs:
        return
    for herb_name in herbs:
        try:
            api_code, items = await smart_search(
                intent="get_herb_by_name",
                herb_name=herb_name,
                cfcode=cfcode,
            )
            real_items = [i for i in items if i.get("_type") != "notice"]
            if not real_items:
                continue
            for it in real_items:
                await redis.publish(
                    channel,
                    json.dumps(
                        {"type": "herb_card", "herb_name": herb_name, "data": it},
                        ensure_ascii=False,
                    ),
                )
        except Exception as e:
            logger.warning("herb_card 조회 실패 (herb=%s): %s", herb_name, e)


# ── 진입점 ────────────────────────────────────────────────────────────────────

async def run_pipeline(
    redis: Redis,
    channel: str,
    chat_history: str,
    question: str,
    cfcode: str | None = None,
) -> str:
    extraction = await _step_llm1(question, chat_history, redis, channel)
    hint = _step_bm25(extraction)
    parsed = await _step_llm2(question, chat_history, extraction, hint, cfcode)

    monograph_block = _step_prefetch_monograph(parsed, hint)
    data_result = await _step_execute(parsed, cfcode, redis, channel)

    answer = await _step_llm3(parsed, data_result, monograph_block, question, chat_history, redis, channel)

    await _step_post_cards(parsed, answer, cfcode, redis, channel)
    return answer
