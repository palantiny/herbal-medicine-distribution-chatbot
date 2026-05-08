"""
History Manager - 128k context 제한 및 요약
대화 히스토리가 CONTEXT_MAX_TOKENS를 초과하면 LLM으로 요약하여 압축.
"""
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 히스토리가 없을 때 반환하는 플레이스홀더 — 다른 모듈에서 이 상수를 import해서 비교하세요.
NO_HISTORY_PLACEHOLDER = "(이전 대화 없음)"

SUMMARY_PROMPT = """다음 대화 내용을 3-5문장으로 요약해 주세요. 핵심 주제와 결론만 포함하세요.
대화:
{text}
요약:"""


def _count_tokens(text: str) -> int:
    """tiktoken으로 토큰 수 계산. 실패 시 문자 수/4 근사."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


async def _summarize_with_llm(text: str) -> str:
    """LLM으로 텍스트 요약."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "user", "content": SUMMARY_PROMPT.format(text=text[:8000])},
            ],
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("Summarize error: %s", e)
        return text[:2000] + "..." if len(text) > 2000 else text


async def get_context_within_limit(
    chat_repo: Any,
    user_id: str,
    session_id: str,
    max_tokens: int | None = None,
    send_fn: Any = None,
) -> str:
    """
    최근 대화를 로드하고, 128k 초과 시 요약하여 context 문자열 반환.
    send_fn이 있으면 "대화 맥락 요약 중..." status 전송.
    """
    max_tokens = max_tokens or settings.CONTEXT_MAX_TOKENS
    limit = 50
    rows = await chat_repo.get_recent(user_id, session_id, limit=limit)

    if not rows:
        return NO_HISTORY_PLACEHOLDER

    lines = [f"{r['role']}: {r['content']}" for r in rows]
    history_str = "\n".join(lines)
    token_count = _count_tokens(history_str)

    if token_count <= max_tokens:
        return history_str

    if send_fn:
        payload = {"type": "status", "content": "대화 맥락 요약 중..."}
        await send_fn(payload)

    # 오래된 턴을 요약하여 압축
    half = len(rows) // 2
    old_part = "\n".join([f"{r['role']}: {r['content']}" for r in rows[:half]])
    recent_part = "\n".join([f"{r['role']}: {r['content']}" for r in rows[half:]])

    summary = await _summarize_with_llm(old_part)
    return f"[이전 대화 요약]\n{summary}\n\n[최근 대화]\n{recent_part}"
