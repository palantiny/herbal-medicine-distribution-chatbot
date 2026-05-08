"""
약재 멘션 추출기 — LLM3 답변에 등장한 약재명을 gpt-4o-mini로 추출.
KNOWLEDGE_FIRST 흐름에서 답변 스트리밍 종료 후 호출되어,
멘션된 약재명을 DJMEDI 사후 조회 → herb_card 이벤트 발행에 사용.
"""
from __future__ import annotations

import logging

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


class MentionedHerbs(BaseModel):
    herbs: list[str] = Field(
        default_factory=list,
        description="답변에 등장한 약재명 목록 (정규화된 한국어 명칭, 중복 제외).",
    )


_SYSTEM_PROMPT = """\
다음 한국어 답변 텍스트에 등장한 한약재명을 모두 추출하세요.

규칙:
1. 한약재(예: 감초, 당귀, 황기, 인삼)에 해당하는 명칭만 추출. 처방명·증상·약리 효능은 제외.
2. 정규화된 표준 한국어 명칭으로 출력 (예: '甘草' → '감초').
3. 중복 제거. 등장 순서 유지.
4. 한약재가 없으면 빈 리스트.
"""


async def extract_mentioned_herbs(answer_text: str) -> list[str]:
    """답변 텍스트에서 약재명 리스트 추출. 실패 시 빈 리스트."""
    if not answer_text or not answer_text.strip():
        return []
    try:
        response = await _get_client().beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": answer_text},
            ],
            response_format=MentionedHerbs,
            temperature=0.0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for h in parsed.herbs:
            if h and h not in seen:
                seen.add(h)
                result.append(h)
        return result
    except Exception as e:
        logger.exception("herb mention extraction error: %s", e)
        return []
