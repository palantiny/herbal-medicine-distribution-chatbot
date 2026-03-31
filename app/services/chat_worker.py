"""
Chat Worker - Redis Queue Consumer
chat_task_queue에서 BRPOP으로 작업을 가져와 process_message 실행.
sql_worker.py 패턴과 동일한 구조.
"""
import asyncio
import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.chat_service import process_message

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_chat_worker(redis: Redis, chat_repo: Any) -> None:
    """
    Chat Worker 메인 루프.
    chat_task_queue에서 BRPOP으로 작업을 가져와 process_message 실행.
    에러 발생 시 Pub/Sub로 에러 이벤트 발행 후 계속.
    """
    logger.info("Chat Worker started")
    while True:
        try:
            result = await redis.brpop(settings.CHAT_TASK_QUEUE, timeout=5)
            if result is None:
                continue

            _, payload_str = result
            payload = json.loads(payload_str)

            session_id = payload["session_id"]
            user_id = payload["user_id"]
            message = payload["message"]

            logger.info(
                "Chat Worker processing: session_id=%s, user_id=%s, message=%s",
                session_id, user_id, message,
            )

            try:
                await process_message(
                    chat_repo=chat_repo,
                    redis=redis,
                    session_id=session_id,
                    user_id=user_id,
                    message=message,
                )
            except Exception as e:
                logger.exception("Chat Worker process_message error: %s", e)
                channel = f"{settings.CHAT_STREAM_PREFIX}{session_id}"
                error_event = json.dumps(
                    {"type": "error", "content": f"처리 중 오류가 발생했습니다: {e}"},
                    ensure_ascii=False,
                )
                await redis.publish(channel, error_event)
                end_event = json.dumps({"type": "end", "content": ""}, ensure_ascii=False)
                await redis.publish(channel, end_event)

        except asyncio.CancelledError:
            logger.info("Chat Worker cancelled")
            break
        except Exception as e:
            logger.exception("Chat Worker error: %s", e)
            await asyncio.sleep(1)
