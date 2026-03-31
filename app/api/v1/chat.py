"""
Chat API — MQ + Pub/Sub 아키텍처
POST /{session_id}/message: 메시지를 Redis Queue에 넣고 즉시 200 OK 반환.
GET  /{session_id}/stream:  Redis Pub/Sub 구독으로 SSE 스트리밍.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    """채팅 요청 Body."""

    message: str = Field(..., min_length=1, description="사용자 질문 내용")
    user_id: str | None = Field(None, description="인증된 user_id (session_id에서 파싱 가능 시 생략)")


def _sse_format(data: dict) -> str:
    """SSE 표준 포맷: data: {JSON}\n\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_user_id_from_session(session_id: str) -> str | None:
    """session_id가 {user_id}_{timestamp} 형식이면 user_id 추출."""
    parts = session_id.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return None


@router.post("/{session_id}/message")
async def post_chat_message(session_id: str, body: ChatMessageRequest, request: Request):
    """
    POST /api/v1/chat/{session_id}/message
    1. user_id 파싱
    2. MongoDB에 user message 즉시 저장
    3. Redis LPUSH chat_task_queue
    4. 즉시 200 OK 반환
    """
    user_id = body.user_id or _parse_user_id_from_session(session_id)
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id required (in body or session_id)")

    chat_repo = getattr(request.app.state, "chat_repo", None)
    if not chat_repo:
        raise HTTPException(status_code=500, detail="chat_repo not initialized")

    redis = await get_redis()

    # user message를 MongoDB에 즉시 저장 (워커 처리 전 영속화)
    await chat_repo.save(session_id, user_id, "user", body.message)

    # Redis Queue에 작업 추가
    task_payload = json.dumps(
        {
            "session_id": session_id,
            "user_id": user_id,
            "message": body.message,
        },
        ensure_ascii=False,
    )
    await redis.lpush(settings.CHAT_TASK_QUEUE, task_payload)

    return {"status": "queued", "session_id": session_id}


@router.get("/{session_id}/stream")
async def get_chat_stream(session_id: str, request: Request):
    """
    GET /api/v1/chat/{session_id}/stream
    Redis Pub/Sub 구독으로 SSE 이벤트 스트리밍.
    클라이언트는 이 엔드포인트를 먼저 연결한 뒤 POST /message를 호출해야 함.
    """
    redis = await get_redis()
    channel = f"{settings.CHAT_STREAM_PREFIX}{session_id}"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                # 클라이언트 연결 끊김 감지
                if await request.is_disconnected():
                    break

                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    continue

                if msg["type"] == "message":
                    data = json.loads(msg["data"])
                    yield _sse_format(data)

                    if data.get("type") == "end":
                        break
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled: session_id=%s", session_id)
        except Exception as e:
            logger.exception("SSE stream error: %s", e)
            yield _sse_format({"type": "error", "content": str(e)})
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{session_id}/history")
async def delete_chat_history(session_id: str, request: Request, user_id: str | None = None):
    """
    DELETE /api/v1/chat/{session_id}/history
    주어진 세션(또는 사용자)의 채팅 기록을 삭제.
    """
    chat_repo = getattr(request.app.state, "chat_repo", None)
    if not chat_repo:
        raise HTTPException(status_code=500, detail="chat_repo not initialized")

    parsed_user = user_id or _parse_user_id_from_session(session_id)
    if hasattr(chat_repo, "clear_history"):
        await chat_repo.clear_history(session_id, parsed_user)
        return {"status": "deleted"}
    return {"status": "skipped", "detail": "Repository does not support clearing"}
