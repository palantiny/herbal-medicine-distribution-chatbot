"""
챗봇 파이프라인 (더미데이터 기반, 단순화).

흐름:
  1) 라우팅(구조화 출력): intent(chat/add_to_cart) + cart_items + mentioned_herbs
  2) add_to_cart면 더미 약재에서 id 매핑 → add_to_cart 이벤트 발행
  3) 더미 카탈로그 + 모노그래프 효능 자료로 답변 토큰 스트리밍

run_chatbot()은 SSE 이벤트(dict)를 yield하는 async generator.
Redis/worker/Neo4j/DynamoDB/DJMEDI 없이 OpenAI 호출만으로 동작.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.data.dummy_herbs import find_by_name, format_catalog_for_prompt
from app.services.monograph_service import format_many_for_prompt, lookup_for_herbs
from app.utils.prompts import (
    ANSWER_SYSTEM_PROMPT,
    ANSWER_USER_TEMPLATE,
    ROUTER_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_MODEL = "gpt-5.4-mini"

# thinking(생각 중) 타이핑 효과 — 답변 대기 동안 상호작용 느낌을 준다.
_THINKING_DELAY = 0.05  # 글자당 지연(초)
_WAITING_THINKING = [
    "질문을 이해하고 있어요",
    "판매 중인 약재를 살펴보고 있어요",
    "필요한 정보를 확인하고 있어요",
]

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


# ── 라우팅 구조화 출력 스키마 ─────────────────────────────────────────────────
class CartItem(BaseModel):
    herb_name: str = Field(description="약재명")
    quantity: int = Field(default=1, description="수량")


class ChatRoute(BaseModel):
    intent: Literal["chat", "add_to_cart"] = Field(description="요청 의도")
    cart_items: list[CartItem] = Field(default_factory=list, description="담을 약재 목록")
    mentioned_herbs: list[str] = Field(default_factory=list, description="언급된 약재명 (효능 조회용)")


async def _route(question: str, chat_history: str) -> ChatRoute:
    """사용자 메시지 → 의도/장바구니/언급약재 구조화 추출. 실패 시 chat."""
    user_content = f"[이전 대화]\n{chat_history or '(없음)'}\n\n[사용자 메시지]\n{question}"
    try:
        resp = await _get_client().beta.chat.completions.parse(
            model=_MODEL,
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=ChatRoute,
            temperature=0,
        )
        parsed = resp.choices[0].message.parsed
        if parsed is None:
            return ChatRoute(intent="chat")
        logger.info("route: intent=%s cart=%d herbs=%s", parsed.intent, len(parsed.cart_items), parsed.mentioned_herbs)
        return parsed
    except Exception as e:
        logger.exception("라우팅 실패 → chat fallback: %s", e)
        return ChatRoute(intent="chat")


async def _answer_stream(user_content: str) -> AsyncGenerator[str, None]:
    """답변 토큰 스트리밍."""
    try:
        stream = await _get_client().chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            stream=True,
            temperature=0.3,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        logger.exception("답변 스트리밍 실패: %s", e)
        yield "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


def _resolve_cart_items(items: list[CartItem]) -> list[dict]:
    """라우팅이 추출한 약재명을 더미 약재 id/가격에 매핑. 판매 목록에 없으면 제외."""
    resolved: list[dict] = []
    for item in items:
        herb = find_by_name(item.herb_name)
        if not herb:
            continue
        qty = item.quantity if item.quantity and item.quantity > 0 else 1
        resolved.append(
            {
                "herb_id": herb["id"],
                "herb_name": herb["name"],
                "price": herb["price"],
                "quantity": qty,
            }
        )
    return resolved


def _build_context_thinking(route: ChatRoute) -> str:
    """라우팅 결과로 '지금 무엇을 하는 중인지' 한 문장 생성."""
    if route.intent == "add_to_cart" and route.cart_items:
        names = ", ".join(i.herb_name for i in route.cart_items)
        return f"{names} 장바구니에 담을 준비를 하고 있어요"
    herbs = route.mentioned_herbs or [i.herb_name for i in route.cart_items]
    if herbs:
        return f"{', '.join(herbs)} 정보를 정리하고 있어요"
    return "답변을 준비하고 있어요"


async def run_chatbot(question: str, chat_history: str = "") -> AsyncGenerator[dict, None]:
    """챗봇 한 턴 실행. SSE 이벤트(dict)를 순서대로 yield.

    이벤트 타입:
      {"type": "thinking_token", "content": "..."}  (답변 대기 중 생각 표시)
      {"type": "add_to_cart", "items": [{herb_id, herb_name, price, quantity}]}
      {"type": "token", "content": "..."}
    (end 이벤트는 호출측에서 발행)
    """
    # 라우팅을 백그라운드로 시작하고, 대기 시간 동안 thinking을 글자 단위로 타이핑한다.
    route_task = asyncio.create_task(_route(question, chat_history))
    for msg in _WAITING_THINKING:
        if route_task.done():
            break
        for ch in msg + "\n":
            yield {"type": "thinking_token", "content": ch}
            await asyncio.sleep(_THINKING_DELAY)
            if route_task.done():
                break
    route = await route_task

    # 라우팅 결과 기반 맥락 thinking (무엇을 하는 중인지 자연스럽게 표시)
    for ch in _build_context_thinking(route):
        yield {"type": "thinking_token", "content": ch}
        await asyncio.sleep(_THINKING_DELAY)

    # 장바구니 담기 처리
    cart_result = "(없음)"
    if route.intent == "add_to_cart":
        resolved = _resolve_cart_items(route.cart_items)
        if resolved:
            yield {"type": "add_to_cart", "items": resolved}
            cart_result = "\n".join(
                f"- {r['herb_name']} {r['quantity']}개 (개당 {r['price']:,}원)" for r in resolved
            )
        else:
            cart_result = "요청하신 약재를 판매 목록에서 찾지 못해 담지 못했습니다."

    # 효능 자료 조회 (언급 약재 + 담은 약재)
    herb_names = list(route.mentioned_herbs) + [i.herb_name for i in route.cart_items]
    monos = lookup_for_herbs(herb_names) if herb_names else {}
    monograph_block = format_many_for_prompt(monos) or "(없음)"

    # 답변 스트리밍
    user_content = ANSWER_USER_TEMPLATE.format(
        catalog=format_catalog_for_prompt(),
        monograph_block=monograph_block,
        chat_history=chat_history or "(없음)",
        cart_result=cart_result,
        question=question,
    )
    async for token in _answer_stream(user_content):
        yield {"type": "token", "content": token}
