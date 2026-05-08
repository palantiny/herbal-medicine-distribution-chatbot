"""
파이프라인 단계별 테스트 스크립트
실행: python test_pipeline.py [질문]
예시: python test_pipeline.py "영천 감초 한 근 주문할래"
"""
import asyncio
import sys
import os

# .env 로드
from dotenv import load_dotenv
load_dotenv()

QUESTION = sys.argv[1] if len(sys.argv) > 1 else "영천 감초 한 근 주문할래"
CFCODE   = sys.argv[2] if len(sys.argv) > 2 else "dj"
SEP = "─" * 60


# ──────────────────────────────────────────────────────────
# Step 1 — LLM1 엔티티 추출
# ──────────────────────────────────────────────────────────
async def test_llm1():
    from app.services.entity_extractor import extract_entities
    print(f"\n{'━'*60}")
    print("STEP 1 │ LLM1 엔티티 추출 (gpt-4o-mini)")
    print(SEP)
    print(f"  질문: {QUESTION}")

    result = await extract_entities(QUESTION, "(이전 대화 없음)")

    print(f"  needs_db : {result.needs_db}")
    print(f"  entities :")
    for e in result.entities:
        print(f"    [{e.slot}] '{e.surface}'")
    return result


# ──────────────────────────────────────────────────────────
# Step 2 — BM25 Scheme Resolver
# ──────────────────────────────────────────────────────────
def test_bm25(extraction):
    from app.services.scheme_resolver import resolve_entities, format_hints_for_prompt

    print(f"\n{'━'*60}")
    print("STEP 2 │ BM25 Scheme Resolver (in-process)")
    print(SEP)

    hint = resolve_entities(extraction.entities)
    hints_text = format_hints_for_prompt(hint)

    print(hints_text)
    return hint


# ──────────────────────────────────────────────────────────
# Step 3 — LLM2 라우팅
# ──────────────────────────────────────────────────────────
async def test_llm2(extraction, hint):
    from app.services.scheme_resolver import format_hints_for_prompt
    from app.services.pipeline import _get_client, Llm2Output
    from app.utils.prompts import LLM2_SYSTEM_PROMPT as V2_LLM2_SYSTEM_PROMPT, LLM2_USER_TEMPLATE as V2_LLM2_USER_TEMPLATE

    print(f"\n{'━'*60}")
    print("STEP 3 │ LLM2 라우팅 + 쿼리 플래닝 (gpt-4o)")
    print(SEP)

    hints_text = format_hints_for_prompt(hint)
    needs_db = "예" if extraction.needs_db else "아니오 (LLM1이 일반 대화로 판정함)"

    user_content = V2_LLM2_USER_TEMPLATE.format(
        chat_history="(이전 대화 없음)",
        needs_db=needs_db,
        sql_hints=hints_text,
        question=QUESTION,
    )

    response = await _get_client().beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": V2_LLM2_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        response_format=Llm2Output,
        temperature=0.1,
    )
    parsed = response.choices[0].message.parsed

    print(f"  mode   : {parsed.mode}")
    print(f"  reason : {parsed.reason}")
    if parsed.mode == "SQL":
        print(f"  sql    : {parsed.sql}")
    if parsed.mode == "DJMEDI_API" and parsed.djmedi_query:
        q = parsed.djmedi_query
        print(f"  intent      : {q.intent}")
        print(f"  maker_name  : {q.maker_name}")
        print(f"  herb_name   : {q.herb_name}")
        print(f"  origin      : {q.origin}")
    if parsed.mode == "DIRECT_ANSWER":
        print(f"  answer : {(parsed.direct_answer or '')[:200]}")

    return parsed


# ──────────────────────────────────────────────────────────
# Step 4 — DJMEDI API 실행
# ──────────────────────────────────────────────────────────
async def test_djmedi(parsed):
    if parsed.mode != "DJMEDI_API" or not parsed.djmedi_query:
        print(f"\n{'━'*60}")
        print("STEP 4 │ DJMEDI API (건너뜀 — mode가 DJMEDI_API 아님)")
        return "(DJMEDI_API 분기 아님)"

    from app.services.djmedi_service import smart_search, format_djmedi_result

    print(f"\n{'━'*60}")
    print("STEP 4 │ DJMEDI API 호출")
    print(SEP)

    q = parsed.djmedi_query
    api_code, items = await smart_search(
        intent=q.intent,
        maker_name=q.maker_name,
        herb_name=q.herb_name,
        origin=q.origin,
        cfcode=CFCODE,
    )
    result_text = format_djmedi_result(api_code, items)

    # 처음 10건만 출력
    lines = result_text.split("\n")
    preview = "\n".join(lines[:11])
    if len(lines) > 11:
        preview += f"\n  ... (총 {len(items)}건)"
    print(preview)
    return result_text


# ──────────────────────────────────────────────────────────
# Step 5 — LLM3 최종 답변
# ──────────────────────────────────────────────────────────
async def test_llm3(data_result: str):
    from app.services.pipeline import _get_client
    from app.utils.prompts import LLM3_SYSTEM_PROMPT as V2_LLM3_SYSTEM_PROMPT, LLM3_USER_TEMPLATE as V2_LLM3_USER_TEMPLATE

    print(f"\n{'━'*60}")
    print("STEP 5 │ LLM3 최종 답변 합성 (gpt-4o)")
    print(SEP)

    user_content = V2_LLM3_USER_TEMPLATE.format(
        data_result=data_result,
        chat_history="(이전 대화 없음)",
        question=QUESTION,
    )

    response = await _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": V2_LLM3_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    print(answer)
    return answer


# ──────────────────────────────────────────────────────────
# KNOWLEDGE_FIRST 시나리오 — 모노그래프 + 사후 카드
# ──────────────────────────────────────────────────────────
async def test_knowledge_first():
    from redis.asyncio import Redis
    from app.services.pipeline import run_pipeline

    print(f"\n{'━'*60}")
    print("KNOWLEDGE_FIRST │ 모노그래프 + 사후 카드 부착")
    print(SEP)
    print(f"  질문: {QUESTION}")

    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    channel = "smoke:knowledge_first"

    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    async def consume():
        async for msg in pubsub.listen():
            if msg.get("type") == "message":
                print(f"  ← {msg['data'][:200]}")

    consume_task = asyncio.create_task(consume())
    try:
        answer = await run_pipeline(redis, channel, "(이전 대화 없음)", QUESTION, CFCODE)
        print(f"\n  최종 답변: {answer[:300]}...")
    finally:
        consume_task.cancel()
        await pubsub.unsubscribe(channel)
        await redis.close()


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────
async def main():
    print(f"\n{'━'*60}")
    print(f"  파이프라인 테스트")
    print(f"  질문  : {QUESTION}")
    print(f"  cfcode: {CFCODE}")
    print(f"{'━'*60}")

    if len(sys.argv) > 3 and sys.argv[3] == "knowledge":
        await test_knowledge_first()
        return

    extraction  = await test_llm1()
    hint        = test_bm25(extraction)
    parsed      = await test_llm2(extraction, hint)
    data_result = await test_djmedi(parsed)
    await test_llm3(data_result)

    print(f"\n{'━'*60}\n  완료\n{'━'*60}\n")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(main())
