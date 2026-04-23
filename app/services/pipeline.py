"""
3단계 순차 LLM 라우팅 파이프라인 (LangGraph 기반)

Stage 1: LLM1 — 구조화 라우터(RouterOutput) + Neo4j 고정 템플릿 병렬 조회 루프
  → DIRECT_ANSWER: direct_response 스트리밍 → END
  → SEARCH_GRAPH: execute_router_graph_search (병렬) → 다시 LLM1 (최대 N회)
  → GENERATE_FINAL_ANSWER: Stage 3 합성(Graph만)
  → CALL_LLM2_SQL: Text-to-SQL → Stage 3 합성

Stage 3: LLM3 — 최종 합성 (Graph + 선택적 SQL 컨텍스트)
"""
import asyncio
import json
import logging
import re
from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph
from redis.asyncio import Redis

from app.core.config import get_settings
from app.schemas.stage1_router import RouterOutput
from app.services.cache_service import get_herb_cache, set_herb_cache, CACHE_PREFIX, DYNAMIC_TTL
from app.services.graph_service import execute_router_graph_search
from app.services.sql_worker import SQL_RESULT_PREFIX, SQL_TASK_QUEUE
from app.utils.prompts import (
    STAGE1_DIRECT_ANSWER_SYSTEM_PROMPT,
    STAGE1_DIRECT_ANSWER_USER_TEMPLATE,
    STAGE1_ROUTER_SYSTEM_PROMPT,
    STAGE1_ROUTER_USER_TEMPLATE,
    STAGE3_SYNTHESIZER_SYSTEM_PROMPT,
    STAGE3_SYNTHESIZER_USER_TEMPLATE,
    TEXT_TO_SQL_SYSTEM_PROMPT,
    TEXT_TO_SQL_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)
settings = get_settings()

Stage1Branch = Literal[
    "DIRECT_ANSWER",
    "SEARCH_GRAPH",
    "GENERATE_FINAL_ANSWER",
    "CALL_LLM2_SQL",
]

AfterGraphBranch = Literal["loop_router", "graph_round_cap"]


class PipelineState(TypedDict):
    """파이프라인 전체 상태."""
    chat_history: str
    question: str
    graph_context: str
    extracted_entities: dict[str, Any]
    sql_redis_context: str
    final_answer: str
    redis: Any
    channel: str
    status_callback: Any
    stage1_route: Stage1Branch
    stage1_iteration: int
    stage1_max_iterations: int
    last_router_output: dict[str, Any] | None


async def _call_llm_text(system_prompt: str, user_content: str) -> str:
    """LLM 비스트리밍 호출 (Text-to-SQL 등)."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
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


# ── 단계별 사고 과정 프롬프트 ─────────────────────────
_THINKING_ROUTER_SYSTEM = (
    "당신은 한약재 유통 챗봇 팔란티니입니다. "
    "사용자 질문을 분석한 내부 사고 과정을 자연스러운 독백으로 2~3문장, 한국어로 작성하세요. "
    "어떤 정보가 필요하고 왜 그 방식을 선택했는지 설명하세요. "
    "답변 자체는 쓰지 말고 분석과 계획만 서술하세요."
)
_THINKING_GRAPH_SYSTEM = (
    "당신은 한약재 유통 챗봇 팔란티니입니다. "
    "지식 그래프에서 어떤 데이터를 탐색할지 내부 사고 과정을 자연스러운 독백으로 2~3문장, 한국어로 작성하세요."
)
_THINKING_SQL_SYSTEM = (
    "당신은 한약재 유통 챗봇 팔란티니입니다. "
    "데이터베이스에서 어떤 정보를 조회할지 내부 사고 과정을 자연스러운 독백으로 2~3문장, 한국어로 작성하세요."
)
_THINKING_SYNTHESIS_SYSTEM = (
    "당신은 한약재 유통 챗봇 팔란티니입니다. "
    "수집된 데이터를 바탕으로 답변을 어떻게 구성할지 내부 사고 과정을 자연스러운 독백으로 2~3문장, 한국어로 작성하세요. "
    "답변 자체는 쓰지 말고 답변 전략만 서술하세요."
)


async def _stream_thinking(
    system_prompt: str,
    user_content: str,
    redis: Redis,
    channel: str,
    max_tokens: int = 200,
) -> None:
    """사고 과정을 thinking_token SSE 이벤트로 스트리밍. gpt-5.4-mini 사용."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=True,
            temperature=0.4,
            max_completion_tokens=max_tokens,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                payload = json.dumps({"type": "thinking_token", "content": token}, ensure_ascii=False)
                await redis.publish(channel, payload)
    except Exception as e:
        logger.warning("Thinking stream error: %s", e)
    # 단계 구분용 빈 줄 추가
    await redis.publish(
        channel,
        json.dumps({"type": "thinking_token", "content": "\n\n"}, ensure_ascii=False),
    )


async def _call_stage1_router_llm(
    chat_history: str,
    graph_context: str,
    question: str,
) -> RouterOutput | None:
    """LLM1 구조화 출력 (Pydantic RouterOutput)."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        user_content = STAGE1_ROUTER_USER_TEMPLATE.format(
            chat_history=chat_history,
            graph_context=graph_context if graph_context.strip() else "(없음)",
            question=question,
        )
        response = await client.beta.chat.completions.parse(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": STAGE1_ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format=RouterOutput,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            logger.warning("Stage1 router: parsed is None (refusal or empty)")
        return parsed
    except Exception as e:
        logger.exception("Stage1 router LLM error: %s", e)
        return None


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
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=True,
            temperature=0.2,
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


async def _fallback_extract_herb_name(question: str, redis: Redis) -> str | None:
    """LLM이 herb_name을 추출하지 못했을 때, Redis 캐시 키 목록에서 직접 매칭."""
    try:
        cursor = "0"
        herb_names: list[str] = []
        while cursor:
            cursor, keys = await redis.scan(
                cursor=cursor,
                match=f"{CACHE_PREFIX}*",
                count=500,
            )
            for key in keys:
                name = key.decode() if isinstance(key, bytes) else key
                name = name.replace(CACHE_PREFIX, "", 1)
                herb_names.append(name)
            if cursor == 0:
                break

        herb_names.sort(key=len, reverse=True)
        for name in herb_names:
            if name in question:
                logger.info("Fallback 약재명 추출: '%s' (from question)", name)
                return name
    except Exception as e:
        logger.warning("Fallback herb name extraction 오류: %s", e)
    return None


def _extract_herb_product_mapping(graph_context: str) -> dict[str, str]:
    """
    graph_context에서 '약재명 → 첫 번째 product_id' 매핑을 추출.
    지원 패턴:
      1) "약재: 이름 [연결된 product_id: PID1, PID2]"
      2) "  - 이름 [연결된 product_id: PID1, PID2]"  (bullet list)
    """
    mapping: dict[str, str] = {}
    pattern = re.compile(r'(?:약재:\s*|[-·]\s+)(\S+?)\s+\[연결된 product_id:\s*([^\]]+)\]')
    for m in pattern.finditer(graph_context):
        name = m.group(1).strip()
        first_pid = m.group(2).split(',')[0].strip()
        if name and first_pid:
            mapping.setdefault(name, first_pid)
    return mapping


def _apply_product_links(text: str, herb_product_map: dict[str, str]) -> str:
    """
    LLM 출력에서 graph_context에 product_id가 확인된 약재명에만 링크 추가.
    이미 마크다운 링크([text](url))로 작성된 부분은 건드리지 않음.
    """
    if not herb_product_map:
        return text

    # 기존 마크다운 링크를 임시 플레이스홀더로 보호
    placeholders: list[str] = []

    def _protect(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00L{len(placeholders) - 1}\x00"

    protected = re.sub(r'\[[^\]]*\]\([^)]+\)', _protect, text)

    # 긴 이름 먼저 처리해서 부분 문자열 치환 방지
    for herb_name in sorted(herb_product_map, key=len, reverse=True):
        pid = herb_product_map[herb_name]
        protected = protected.replace(herb_name, f"[{herb_name}](/product/{pid})")

    # 플레이스홀더 복원
    for i, original in enumerate(placeholders):
        protected = protected.replace(f"\x00L{i}\x00", original)

    return protected


async def _publish_status(state: PipelineState, message: str) -> None:
    payload = json.dumps({"type": "status", "content": message}, ensure_ascii=False)
    await state["redis"].publish(state["channel"], payload)


def _sync_extracted_entities_from_router(state: PipelineState) -> None:
    """RouterOutput.extracted_nodes에서 herb_name 등을 동기화."""
    raw = state.get("last_router_output") or {}
    nodes = raw.get("extracted_nodes") or []
    state["extracted_entities"] = dict(state.get("extracted_entities") or {})
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if n.get("node_type") == "Herb" and n.get("node_name"):
            state["extracted_entities"]["herb_name"] = n["node_name"]
            return


def _router_fallback(reason: str) -> RouterOutput:
    return RouterOutput(
        route="CALL_LLM2_SQL",
        reason=reason,
        target_intents=[],
        extracted_nodes=[],
        direct_response="",
    )


async def stage1_router(state: PipelineState) -> PipelineState:
    """Stage 1: 1차 라우팅 — 직접 답변 vs Cypher(Graph DB) 조회 결정."""
    parsed = await _call_stage1_router_llm(
        state["chat_history"],
        state["graph_context"],
        state["question"],
    )
    if parsed is None:
        parsed = _router_fallback("라우터 JSON 파싱/호출 실패 — SQL 경로로 진행")

    if (
        parsed.route == "SEARCH_GRAPH"
        and state["stage1_iteration"] >= state["stage1_max_iterations"]
    ):
        parsed = RouterOutput(
            route="GENERATE_FINAL_ANSWER",
            reason="그래프 탐색 최대 라운드 도달 — 수집된 컨텍스트로 답변",
            target_intents=[],
            extracted_nodes=list(parsed.extracted_nodes),
            direct_response="",
        )

    state["last_router_output"] = parsed.model_dump()
    state["stage1_route"] = parsed.route  # type: ignore[assignment]
    _sync_extracted_entities_from_router(state)

    # 라우팅 결정에 대한 사고 과정 스트리밍
    intents_str = ', '.join(parsed.target_intents) if parsed.target_intents else '없음'
    await _stream_thinking(
        _THINKING_ROUTER_SYSTEM,
        f"사용자 질문: {state['question']}\n"
        f"라우팅 결정: {parsed.route}\n"
        f"조회 유형: {intents_str}\n"
        f"근거: {parsed.reason or '없음'}",
        state["redis"], state["channel"],
    )
    return state


def stage1_router_branch(state: PipelineState) -> Stage1Branch:
    return state["stage1_route"]


async def stage1_direct_from_router(state: PipelineState) -> PipelineState:
    """DIRECT_ANSWER: direct_response 우선, 없으면 기존 Stage1 직접 답변 스트림."""
    dr = (state.get("last_router_output") or {}).get("direct_response") or ""
    redis: Redis = state["redis"]
    channel = state["channel"]

    # 직접 답변 전략 사고 과정 스트리밍
    await _stream_thinking(
        _THINKING_SYNTHESIS_SYSTEM,
        f"사용자 질문: {state['question']}\n"
        f"준비된 답변: {dr[:200] if dr else '없음 (즉석 생성)'}",
        redis, channel,
    )

    if dr.strip():
        for ch in dr:
            payload = json.dumps({"type": "token", "content": ch}, ensure_ascii=False)
            await redis.publish(channel, payload)
        state["final_answer"] = dr
        return state

    user_content = STAGE1_DIRECT_ANSWER_USER_TEMPLATE.format(
        chat_history=state["chat_history"],
        question=state["question"],
    )
    answer = await _call_llm_stream(
        STAGE1_DIRECT_ANSWER_SYSTEM_PROMPT,
        user_content,
        redis,
        channel,
    )
    state["final_answer"] = answer
    return state


async def stage1_graph_tool(state: PipelineState) -> PipelineState:
    """SEARCH_GRAPH: 병렬 템플릿 실행 후 graph_context 누적. thinking과 병렬 실행."""
    raw = state.get("last_router_output")
    if not raw:
        state["graph_context"] += "\n[내부 오류] 라우터 출력이 없습니다.\n"
        return state
    try:
        router = RouterOutput.model_validate(raw)
    except Exception as e:
        logger.warning("last_router_output 검증 실패: %s", e)
        state["graph_context"] += f"\n[내부 오류] 라우터 출력 형식 오류: {e}\n"
        return state

    intents_str = ', '.join(router.target_intents) if router.target_intents else '없음'
    nodes_str = ', '.join(
        f"{n.node_type}:{n.node_name}" for n in router.extracted_nodes if n.node_name
    ) or '없음'

    # 그래프 탐색과 thinking 스트리밍을 병렬 실행 (탐색 대기 시간 중 thinking 표시)
    _, chunk = await asyncio.gather(
        _stream_thinking(
            _THINKING_GRAPH_SYSTEM,
            f"탐색 유형: {intents_str}\n대상 노드: {nodes_str}\n사용자 질문: {state['question']}",
            state["redis"], state["channel"],
        ),
        execute_router_graph_search(router),
    )

    state["graph_context"] = (state["graph_context"] or "") + chunk
    state["stage1_iteration"] = state["stage1_iteration"] + 1
    _sync_extracted_entities_from_router(state)
    return state


def stage1_after_graph_branch(state: PipelineState) -> AfterGraphBranch:
    if state["stage1_iteration"] >= state["stage1_max_iterations"]:
        return "graph_round_cap"
    return "loop_router"


async def stage1_skip_to_synthesizer(state: PipelineState) -> PipelineState:
    """그래프 라운드 상한 도달 시 Stage3로 직행."""
    return state


async def stage2_execute_sql(state: PipelineState) -> PipelineState:
    """CALL_LLM2_SQL: Redis 캐시 우선 → Text-to-SQL."""
    redis: Redis = state["redis"]
    question = state["question"]
    herb_name = (state["extracted_entities"] or {}).get("herb_name")

    if not herb_name:
        herb_name = await _fallback_extract_herb_name(question, redis)
        if herb_name:
            state["extracted_entities"] = state.get("extracted_entities") or {}
            state["extracted_entities"]["herb_name"] = herb_name

    # DB 조회 전 사고 과정 스트리밍
    await _stream_thinking(
        _THINKING_SQL_SYSTEM,
        f"사용자 질문: {question}\n약재명: {herb_name or '미상'}",
        redis, state["channel"],
    )

    if herb_name:
        try:
            cache_data = await get_herb_cache(herb_name)
            if cache_data:
                logger.info("Cache HIT: '%s' → SQL 실행 생략", herb_name)
                cache_result = json.dumps(cache_data, ensure_ascii=False, indent=2)
                state["sql_redis_context"] = (
                    f"--- 캐시 데이터 (herb: {herb_name}) ---\n{cache_result}"
                )
                return state
        except Exception as e:
            logger.warning("Cache 조회 오류 (%s), SQL fallback: %s", herb_name, e)

    if herb_name:
        logger.info("Cache MISS: '%s' → SQL 실행", herb_name)
    else:
        logger.info("herb_name 미추출 → SQL 실행")

    sql_result = await _execute_sql_via_redis(question, redis)

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
                    herb_name,
                    len(sql_data),
                    DYNAMIC_TTL,
                )
        except (json.JSONDecodeError, Exception) as e:
            logger.debug("SQL 결과 캐시 저장 실패: %s", e)

    state["sql_redis_context"] = (
        f"--- DB 조회 결과 ---\n{sql_result}" if sql_result else ""
    )
    return state


async def _execute_sql_via_redis(message: str, redis: Redis) -> str:
    sql = await _call_llm_text(
        TEXT_TO_SQL_SYSTEM_PROMPT,
        TEXT_TO_SQL_USER_TEMPLATE.format(message=message),
    )
    sql = sql.split("--")[0].strip()

    if not sql or not sql.upper().startswith("SELECT"):
        logger.info(
            "Text-to-SQL 거부 (SELECT 아님): message=%r sql=%r",
            message[:800] if len(message) > 800 else message,
            sql[:2000] if len(sql) > 2000 else sql,
        )
        return "재고/단가 조회는 SELECT 쿼리만 가능합니다."

    task_id = str(uuid4())
    result_key = f"{SQL_RESULT_PREFIX}{task_id}"
    task_payload = json.dumps(
        {"task_id": task_id, "sql": sql, "result_key": result_key},
        ensure_ascii=False,
    )

    logger.info(
        "Text-to-SQL 생성: task_id=%s message=%r sql=%s",
        task_id,
        message[:800] if len(message) > 800 else message,
        sql,
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
    sql_ctx = state.get("sql_redis_context") or ""
    if not sql_ctx.strip():
        sql_ctx = "(SQL/RDB 조회 없음)"

    # 답변 합성 전 사고 과정 스트리밍
    ctx_preview = (state["graph_context"] or "")[:400]
    await _stream_thinking(
        _THINKING_SYNTHESIS_SYSTEM,
        f"사용자 질문: {state['question']}\n수집된 데이터: {ctx_preview}",
        state["redis"], state["channel"],
    )

    user_content = STAGE3_SYNTHESIZER_USER_TEMPLATE.format(
        graph_context=state["graph_context"] or "(없음)",
        sql_redis_context=sql_ctx,
        chat_history=state["chat_history"],
        question=state["question"],
    )
    answer = await _call_llm_stream(
        STAGE3_SYNTHESIZER_SYSTEM_PROMPT,
        user_content,
        state["redis"],
        state["channel"],
    )

    # 후처리: graph_context의 product_id 기반으로 누락된 약재명 링크 보완
    herb_map = _extract_herb_product_mapping(state.get("graph_context") or "")
    corrected = _apply_product_links(answer, herb_map)
    if corrected != answer:
        payload = json.dumps({"type": "correction", "content": corrected}, ensure_ascii=False)
        await state["redis"].publish(state["channel"], payload)

    state["final_answer"] = corrected
    return state


def build_pipeline_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("stage1_router", stage1_router)
    graph.add_node("stage1_direct_from_router", stage1_direct_from_router)
    graph.add_node("stage1_graph_tool", stage1_graph_tool)
    graph.add_node("stage1_skip_to_synthesizer", stage1_skip_to_synthesizer)
    graph.add_node("stage2_execute_sql", stage2_execute_sql)
    graph.add_node("stage3_synthesizer", stage3_synthesizer)

    graph.set_entry_point("stage1_router")

    graph.add_conditional_edges(
        "stage1_router",
        stage1_router_branch,
        {
            "DIRECT_ANSWER": "stage1_direct_from_router",
            "SEARCH_GRAPH": "stage1_graph_tool",
            "GENERATE_FINAL_ANSWER": "stage3_synthesizer",
            "CALL_LLM2_SQL": "stage2_execute_sql",
        },
    )
    graph.add_edge("stage1_direct_from_router", END)

    graph.add_conditional_edges(
        "stage1_graph_tool",
        stage1_after_graph_branch,
        {
            "loop_router": "stage1_router",
            "graph_round_cap": "stage1_skip_to_synthesizer",
        },
    )
    graph.add_edge("stage1_skip_to_synthesizer", "stage3_synthesizer")
    graph.add_edge("stage2_execute_sql", "stage3_synthesizer")
    graph.add_edge("stage3_synthesizer", END)

    return graph


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_pipeline_graph().compile()
    return _compiled_graph


async def run_pipeline(
    redis: Redis,
    channel: str,
    chat_history: str,
    question: str,
) -> str:
    compiled = get_compiled_graph()

    initial_state: PipelineState = {
        "chat_history": chat_history,
        "question": question,
        "graph_context": "",
        "extracted_entities": {},
        "sql_redis_context": "",
        "final_answer": "",
        "redis": redis,
        "channel": channel,
        "status_callback": None,
        "stage1_route": "GENERATE_FINAL_ANSWER",
        "stage1_iteration": 0,
        "stage1_max_iterations": settings.STAGE1_GRAPH_MAX_ROUNDS,
        "last_router_output": None,
    }

    final_state = await compiled.ainvoke(initial_state)
    return final_state["final_answer"]
