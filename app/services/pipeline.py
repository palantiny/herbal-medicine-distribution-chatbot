"""
3단계 순차 LLM 라우팅 파이프라인 (LangGraph 기반)

Stage 1: LLM 1 — Text-to-Cypher & 1차 라우팅
  → [DIRECT_ANSWER] 즉시 답변 → END
  → [CYPHER] Graph DB 조회 → Stage 2

Stage 2: LLM 2 — Text-to-SQL & 2차 라우팅
  → [DIRECT_ANSWER] Graph 문맥 기반 즉시 답변 → END
  → [SQL] RDB/Redis 조회 → Stage 3

Stage 3: LLM 3 — 최종 합성 답변 (Synthesizer)
  → 모든 컨텍스트 종합 → 맞춤형 답변 → END
"""
import json
import logging
import re
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph
from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.cache_service import get_herb_cache, set_herb_cache, CACHE_PREFIX, DYNAMIC_TTL
from app.services.graph_service import search_herb_graph
from app.services.sql_worker import SQL_RESULT_PREFIX, SQL_TASK_QUEUE
from app.utils.prompts import (
    STAGE1_DIRECT_ANSWER_SYSTEM_PROMPT,
    STAGE1_DIRECT_ANSWER_USER_TEMPLATE,
    STAGE1_ROUTER_SYSTEM_PROMPT,
    STAGE1_ROUTER_USER_TEMPLATE,
    STAGE2_DIRECT_ANSWER_SYSTEM_PROMPT,
    STAGE2_DIRECT_ANSWER_USER_TEMPLATE,
    STAGE2_ROUTER_SYSTEM_PROMPT,
    STAGE2_ROUTER_USER_TEMPLATE,
    STAGE3_SYNTHESIZER_SYSTEM_PROMPT,
    STAGE3_SYNTHESIZER_USER_TEMPLATE,
    TEXT_TO_SQL_SYSTEM_PROMPT,
    TEXT_TO_SQL_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ──────────────────────────────────────────────
# 파이프라인 상태 정의 (TypedDict)
# ──────────────────────────────────────────────

class PipelineState(TypedDict):
    """3단계 파이프라인의 전체 상태."""
    # 입력
    chat_history: str
    question: str
    # 1단계 결과
    stage1_route: str           # "DIRECT_ANSWER" | "CYPHER"
    graph_context: str          # Graph DB 조회 결과
    extracted_entities: dict    # 추출된 엔티티 (herb_name 등)
    # 2단계 결과
    stage2_route: str           # "DIRECT_ANSWER" | "SQL"
    sql_redis_context: str      # RDB/Redis 조회 결과
    # 최종 출력
    final_answer: str
    # 내부 제어
    redis: Any                  # Redis 클라이언트 (노드 간 공유)
    channel: str                # Redis Pub/Sub 채널
    status_callback: Any        # 상태 메시지 발행 콜백


# ──────────────────────────────────────────────
# LLM 호출 유틸리티
# ──────────────────────────────────────────────

async def _call_llm_text(system_prompt: str, user_content: str) -> str:
    """LLM 비스트리밍 호출 (라우팅 판단, SQL 생성 등)."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("LLM text error: %s", e)
        return ""


async def _call_llm_stream(
    system_prompt: str,
    user_content: str,
    redis: Redis,
    channel: str,
) -> str:
    """LLM 스트리밍 호출. Redis Pub/Sub로 토큰 전송."""
    full_response = ""

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=True,
            temperature=0.7,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                payload = json.dumps({"type": "token", "content": token}, ensure_ascii=False)
                await redis.publish(channel, payload)
        return full_response
    except Exception as e:
        logger.exception("LLM stream error: %s", e)
        fallback = "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        for ch in fallback:
            payload = json.dumps({"type": "token", "content": ch}, ensure_ascii=False)
            await redis.publish(channel, payload)
        return fallback


def _parse_json(text: str) -> dict | None:
    """LLM 출력에서 JSON 파싱."""
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


async def _fallback_extract_herb_name(question: str, redis: Redis) -> str | None:
    """LLM이 herb_name을 추출하지 못했을 때, Redis 캐시 키 목록에서 직접 매칭."""
    try:
        cursor = "0"
        herb_names: list[str] = []
        while cursor:
            cursor, keys = await redis.scan(
                cursor=cursor, match=f"{CACHE_PREFIX}*", count=500,
            )
            for key in keys:
                name = key.decode() if isinstance(key, bytes) else key
                name = name.replace(CACHE_PREFIX, "", 1)
                herb_names.append(name)
            if cursor == 0:
                break

        # 긴 이름부터 매칭 (예: '당삼 (만삼)' 우선, '삼' 나중)
        herb_names.sort(key=len, reverse=True)
        for name in herb_names:
            if name in question:
                logger.info("Fallback 약재명 추출: '%s' (from question)", name)
                return name
    except Exception as e:
        logger.warning("Fallback herb name extraction 오류: %s", e)
    return None


async def _publish_status(state: PipelineState, message: str) -> None:
    """상태 메시지를 Redis Pub/Sub로 발행."""
    payload = json.dumps({"type": "status", "content": message}, ensure_ascii=False)
    await state["redis"].publish(state["channel"], payload)


# ──────────────────────────────────────────────
# 노드 함수 정의
# ──────────────────────────────────────────────

async def stage1_router(state: PipelineState) -> PipelineState:
    """Stage 1: 1차 라우팅 — 직접 답변 vs Cypher(Graph DB) 조회 결정."""
    await _publish_status(state, "1단계: 질문 의도 분석 중...")

    question = state["question"]
    chat_history = state["chat_history"]

    user_content = STAGE1_ROUTER_USER_TEMPLATE.format(
        chat_history=chat_history, question=question,
    )
    text = await _call_llm_text(STAGE1_ROUTER_SYSTEM_PROMPT, user_content)
    parsed = _parse_json(text)

    if parsed:
        route = parsed.get("route", "CYPHER").upper()
        if route not in ("DIRECT_ANSWER", "CYPHER"):
            route = "CYPHER"
        state["stage1_route"] = route
        state["extracted_entities"] = parsed.get("extracted_entities", {})
    else:
        state["stage1_route"] = "CYPHER"
        state["extracted_entities"] = {}

    logger.info("Stage1 route=%s, entities=%s", state["stage1_route"], state["extracted_entities"])
    return state


def stage1_route_condition(state: PipelineState) -> str:
    """Stage 1 조건부 엣지: 라우팅 결정에 따라 분기."""
    return state["stage1_route"]


async def stage1_direct_answer(state: PipelineState) -> PipelineState:
    """Stage 1 → 직접 답변 (Early Exit). 추가 조회 없이 즉시 답변."""
    await _publish_status(state, "이전 대화 맥락으로 답변 생성 중...")

    user_content = STAGE1_DIRECT_ANSWER_USER_TEMPLATE.format(
        chat_history=state["chat_history"],
        question=state["question"],
    )
    answer = await _call_llm_stream(
        STAGE1_DIRECT_ANSWER_SYSTEM_PROMPT,
        user_content,
        state["redis"],
        state["channel"],
    )
    state["final_answer"] = answer
    return state


async def stage1_execute_cypher(state: PipelineState) -> PipelineState:
    """Stage 1 → Cypher 실행: Graph DB(지식 그래프) 조회."""
    await _publish_status(state, "한약재 지식 그래프 탐색 중...")

    question = state["question"]
    extracted = state["extracted_entities"]

    graph_result = await search_herb_graph(question, extracted)
    state["graph_context"] = graph_result

    return state


async def stage2_router(state: PipelineState) -> PipelineState:
    """Stage 2: 2차 라우팅 — Graph 결과 기반 직접 답변 vs SQL 조회 결정."""
    await _publish_status(state, "2단계: 추가 데이터 필요성 분석 중...")

    question = state["question"]
    chat_history = state["chat_history"]
    graph_context = state["graph_context"]

    user_content = STAGE2_ROUTER_USER_TEMPLATE.format(
        chat_history=chat_history,
        graph_context=graph_context,
        question=question,
    )
    text = await _call_llm_text(STAGE2_ROUTER_SYSTEM_PROMPT, user_content)
    parsed = _parse_json(text)

    if parsed:
        route = parsed.get("route", "SQL").upper()
        if route not in ("DIRECT_ANSWER", "SQL"):
            route = "SQL"
        state["stage2_route"] = route
    else:
        state["stage2_route"] = "SQL"

    logger.info("Stage2 route=%s", state["stage2_route"])
    return state


def stage2_route_condition(state: PipelineState) -> str:
    """Stage 2 조건부 엣지: 라우팅 결정에 따라 분기."""
    return state["stage2_route"]


async def stage2_direct_answer(state: PipelineState) -> PipelineState:
    """Stage 2 → 직접 답변 (Early Exit). Graph 컨텍스트 기반 답변."""
    await _publish_status(state, "Graph 데이터 기반 답변 생성 중...")

    user_content = STAGE2_DIRECT_ANSWER_USER_TEMPLATE.format(
        graph_context=state["graph_context"],
        chat_history=state["chat_history"],
        question=state["question"],
    )
    answer = await _call_llm_stream(
        STAGE2_DIRECT_ANSWER_SYSTEM_PROMPT,
        user_content,
        state["redis"],
        state["channel"],
    )
    state["final_answer"] = answer
    return state


async def stage2_execute_sql(state: PipelineState) -> PipelineState:
    """Stage 2 → SQL 실행: Redis 캐시 우선 조회, Miss 시에만 SQL 실행."""
    await _publish_status(state, "데이터 조회 중 (캐시 → DB 순서)...")

    redis: Redis = state["redis"]
    question = state["question"]
    herb_name = (state["extracted_entities"] or {}).get("herb_name")

    # ── 0) Fallback: LLM이 herb_name을 못 뽑았으면 질문에서 직접 탐색 ──
    if not herb_name:
        herb_name = await _fallback_extract_herb_name(question, redis)
        if herb_name:
            state["extracted_entities"] = state.get("extracted_entities") or {}
            state["extracted_entities"]["herb_name"] = herb_name

    # ── 1) Cache-First: 약재명이 추출된 경우 Redis 캐시 우선 조회 ──
    if herb_name:
        try:
            cache_data = await get_herb_cache(herb_name)
            if cache_data:
                # ✅ Cache HIT → SQL 실행 건너뛰기
                logger.info("Cache HIT: '%s' → SQL 실행 생략", herb_name)
                cache_result = json.dumps(cache_data, ensure_ascii=False, indent=2)
                state["sql_redis_context"] = (
                    f"--- 캐시 데이터 (herb: {herb_name}) ---\n{cache_result}"
                )
                return state
        except Exception as e:
            logger.warning("Cache 조회 오류 (%s), SQL fallback: %s", herb_name, e)

    # ── 2) Cache MISS 또는 herb_name 미추출 → SQL 실행 ──
    if herb_name:
        logger.info("Cache MISS: '%s' → SQL 실행", herb_name)
    else:
        logger.info("herb_name 미추출 → SQL 실행")

    sql_result = await _execute_sql_via_redis(question, redis)

    # ── 3) Write-Through: SQL 결과를 캐시에 동적 저장 (TTL 1h) ──
    if herb_name and sql_result and not sql_result.startswith("조회 중 오류"):
        try:
            sql_data = json.loads(sql_result)
            if isinstance(sql_data, list) and len(sql_data) > 0:
                cache_payload = {
                    "herb_name": herb_name,
                    "sql_result": sql_data,
                }
                await set_herb_cache(herb_name, cache_payload, ttl=DYNAMIC_TTL)
                logger.info(
                    "Dynamic cache SET: '%s' (%d rows, TTL=%ds)",
                    herb_name, len(sql_data), DYNAMIC_TTL,
                )
        except (json.JSONDecodeError, Exception) as e:
            logger.debug("SQL 결과 캐시 저장 실패: %s", e)

    state["sql_redis_context"] = (
        f"--- DB 조회 결과 ---\n{sql_result}" if sql_result else ""
    )
    return state


async def _execute_sql_via_redis(message: str, redis: Redis) -> str:
    """Redis Queue를 통한 Text-to-SQL 실행."""
    sql = await _call_llm_text(
        TEXT_TO_SQL_SYSTEM_PROMPT,
        TEXT_TO_SQL_USER_TEMPLATE.format(message=message),
    )
    sql = sql.split("--")[0].strip()
    # 복수 쿼리 방지: 세미콜론으로 구분된 경우 첫 번째 쿼리만 사용
    sql = sql.split(";")[0].strip()
    logger.info("Generated SQL: %s", sql)

    if not sql or not sql.upper().startswith("SELECT"):
        return "재고/단가 조회는 SELECT 쿼리만 가능합니다."

    task_id = str(uuid4())
    result_key = f"{SQL_RESULT_PREFIX}{task_id}"
    task_payload = json.dumps(
        {"task_id": task_id, "sql": sql, "result_key": result_key},
        ensure_ascii=False,
    )

    await redis.lpush(SQL_TASK_QUEUE, task_payload)
    result = await redis.blpop(result_key, timeout=30)

    if result is None:
        return "DB 조회 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."

    _, data_str = result
    data = json.loads(data_str)
    if isinstance(data, dict) and "error" in data:
        return f"조회 중 오류: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def stage3_synthesizer(state: PipelineState) -> PipelineState:
    """Stage 3: 모든 컨텍스트 종합 → 최종 맞춤형 답변 생성."""
    await _publish_status(state, "3단계: 수집 데이터 종합 분석 및 최종 답변 생성 중...")

    user_content = STAGE3_SYNTHESIZER_USER_TEMPLATE.format(
        graph_context=state["graph_context"],
        sql_redis_context=state["sql_redis_context"],
        chat_history=state["chat_history"],
        question=state["question"],
    )
    answer = await _call_llm_stream(
        STAGE3_SYNTHESIZER_SYSTEM_PROMPT,
        user_content,
        state["redis"],
        state["channel"],
    )
    state["final_answer"] = answer
    return state


# ──────────────────────────────────────────────
# LangGraph 그래프 빌드
# ──────────────────────────────────────────────

def build_pipeline_graph() -> StateGraph:
    """3단계 순차 파이프라인 LangGraph를 구성하여 반환."""
    graph = StateGraph(PipelineState)

    graph.add_node("stage1_router", stage1_router)
    graph.add_node("stage1_direct_answer", stage1_direct_answer)
    graph.add_node("stage1_execute_cypher", stage1_execute_cypher)
    graph.add_node("stage2_router", stage2_router)
    graph.add_node("stage2_direct_answer", stage2_direct_answer)
    graph.add_node("stage2_execute_sql", stage2_execute_sql)
    graph.add_node("stage3_synthesizer", stage3_synthesizer)

    graph.set_entry_point("stage1_router")

    graph.add_conditional_edges(
        "stage1_router",
        stage1_route_condition,
        {"DIRECT_ANSWER": "stage1_direct_answer", "CYPHER": "stage1_execute_cypher"},
    )
    graph.add_edge("stage1_direct_answer", END)
    graph.add_edge("stage1_execute_cypher", "stage2_router")

    graph.add_conditional_edges(
        "stage2_router",
        stage2_route_condition,
        {"DIRECT_ANSWER": "stage2_direct_answer", "SQL": "stage2_execute_sql"},
    )
    graph.add_edge("stage2_direct_answer", END)
    graph.add_edge("stage2_execute_sql", "stage3_synthesizer")
    graph.add_edge("stage3_synthesizer", END)

    return graph


_compiled_graph = None


def get_compiled_graph():
    """컴파일된 LangGraph 인스턴스를 반환 (지연 초기화)."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_pipeline_graph()
        _compiled_graph = graph.compile()
    return _compiled_graph


async def run_pipeline(
    redis: Redis,
    channel: str,
    chat_history: str,
    question: str,
) -> str:
    """3단계 파이프라인을 실행하고 최종 답변을 반환."""
    compiled = get_compiled_graph()

    initial_state: PipelineState = {
        "chat_history": chat_history,
        "question": question,
        "stage1_route": "",
        "graph_context": "",
        "extracted_entities": {},
        "stage2_route": "",
        "sql_redis_context": "",
        "final_answer": "",
        "redis": redis,
        "channel": channel,
        "status_callback": None,
    }

    final_state = await compiled.ainvoke(initial_state)
    return final_state["final_answer"]
