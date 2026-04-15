"""
Chat Service — LLM 파이프라인 오케스트레이터
"""
import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.history_manager import get_context_within_limit
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)
settings = get_settings()


async def process_message(
    chat_repo: Any,
    redis: Redis,
    session_id: str,
    user_id: str,
    message: str,
    cfcode: str | None = None,
) -> None:
    channel = f"{settings.CHAT_STREAM_PREFIX}{session_id}"

    history_str = await get_context_within_limit(chat_repo, user_id, session_id)

    final_answer = await run_pipeline(
        redis=redis,
        channel=channel,
        chat_history=history_str,
        question=message,
        cfcode=cfcode,
    )

    await redis.publish(channel, json.dumps({"type": "end", "content": ""}, ensure_ascii=False))
    await chat_repo.save(session_id, user_id, "assistant", final_answer)
