"""
LLM1 — 엔티티 추출기 (gpt-4o-mini, structured output)

사용자 질문에서 BM25 alias lookup이 필요한 엔티티를 추출.
슬롯: herb_name / maker / origin / packaging_unit
"""
from __future__ import annotations

import logging
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.history_manager import NO_HISTORY_PLACEHOLDER

logger = logging.getLogger(__name__)
settings = get_settings()

# ── OpenAI 클라이언트 싱글톤 (Fix #7) ─────────────────────────────────────────
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


# ── 출력 스키마 ────────────────────────────────────────────────────────────────
class ExtractedEntity(BaseModel):
    slot: Literal["herb_name", "maker", "origin", "packaging_unit"] = Field(
        description="엔티티 종류"
    )
    surface: str = Field(description="사용자가 입력한 원문 표현 (정규화 전)")


class EntityExtractionOutput(BaseModel):
    entities: list[ExtractedEntity] = Field(
        description="추출된 엔티티 목록. 해당 없으면 빈 리스트.",
        default_factory=list,
    )
    needs_db: bool = Field(
        description=(
            "실제 DB 조회가 필요하면 true. "
            "인사말·일반 상식·대화만으로 답변 가능하면 false."
        )
    )


# ── 시스템 프롬프트 ────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
당신은 한약재 유통 B2B 챗봇의 전처리 엔진입니다.
사용자 질문에서 다음 4가지 슬롯에 해당하는 엔티티를 추출하세요.

[슬롯 정의]
- herb_name : 약재명 (예: 감초, 당귀, 황기, 백출)
- maker     : 제조사·약품회사 (예: 씨케이, CK, 광명당, 바른한방, 디제이, 영천, 허브팜, 채움생, 대연제약, 휴먼허브)
- origin    : 원산지·국가 (예: 국산, 중국산, 수입, 한국)
- packaging_unit : 포장 단위·용량 (예: 한근, 600g, 반근, 300g)

[규칙]
1. 사용자가 쓴 원문 표현 그대로 surface에 기록하세요. 정규화하지 마세요.
2. 동일 슬롯의 엔티티가 여러 개면 모두 추출하세요.
3. 인사·일반 대화·한의학 지식(효능/성미/귀경 등)은 needs_db=false로 설정하세요.
4. 재고, 가격, 입출고, 약재 목록 조회 등 DB가 필요한 질문은 needs_db=true로 설정하세요.
5. 이전 대화 맥락도 함께 참고하여 생략된 엔티티를 보완하세요.
6. '씨케이황기', '휴먼감초'처럼 제조사명이 붙은 약재명은 maker와 herb_name 두 슬롯으로 분리해 추출하세요.
"""


# ── 퍼블릭 함수 ───────────────────────────────────────────────────────────────
async def extract_entities(
    question: str,
    chat_history: str,
) -> EntityExtractionOutput:
    """
    LLM1으로 엔티티 추출.
    실패 시 빈 출력(entities=[], needs_db=True) 반환 → 파이프라인 계속 진행.
    """
    # Fix #10: NO_HISTORY_PLACEHOLDER 상수로 비교
    has_history = (
        bool(chat_history)
        and chat_history.strip()
        and chat_history != NO_HISTORY_PLACEHOLDER
    )
    user_content = (
        f"[이전 대화]\n{chat_history}\n\n[사용자 질문]\n{question}"
        if has_history
        else f"[사용자 질문]\n{question}"
    )

    try:
        response = await _get_client().beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=EntityExtractionOutput,
            temperature=0.0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            logger.warning("LLM1: parsed output is None")
            return EntityExtractionOutput(entities=[], needs_db=True)

        logger.info(
            "LLM1 추출: needs_db=%s, entities=%s",
            parsed.needs_db,
            [(e.slot, e.surface) for e in parsed.entities],
        )
        return parsed

    except Exception as e:
        logger.exception("LLM1 entity extraction error: %s", e)
        return EntityExtractionOutput(entities=[], needs_db=True)
