"""
Chat API — 더미데이터 기반 단순 SSE 스트리밍.

POST /{session_id}/message : 메시지를 받아 SSE로 답변을 직접 스트리밍.
                            대화 맥락은 클라이언트가 history로 함께 전송(백엔드 무상태).
DELETE /{session_id}/history : 무상태이므로 no-op (클라이언트 호환용).

Redis MQ / worker / Neo4j / SQL / DynamoDB / DJMEDI 없이 OpenAI 호출만으로 동작.
"""
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.chatbot_pipeline import run_chatbot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_HISTORY_LIMIT = 10  # 답변에 사용할 최근 대화 턴 수
_ROLE_LABEL = {"user": "사용자", "assistant": "상담원"}


class HistoryItem(BaseModel):
    role: str
    content: str


class ChatMessageRequest(BaseModel):
    """채팅 요청 Body."""

    message: str = Field(..., min_length=1, description="사용자 질문 내용")
    history: list[HistoryItem] | None = Field(default=None, description="최근 대화 (클라이언트 보관)")
    # 하위 호환용 — 더미 모드에서는 사용하지 않음
    user_id: str | None = None
    cfcode: str | None = None


def _sse_format(data: dict) -> str:
    """SSE 표준 포맷: data: {JSON}\n\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _format_history(history: list[HistoryItem] | None) -> str:
    """최근 대화를 '사용자: ... / 상담원: ...' 텍스트로 변환."""
    if not history:
        return ""
    recent = history[-_HISTORY_LIMIT:]
    lines = []
    for m in recent:
        if not m.content:
            continue
        label = _ROLE_LABEL.get(m.role, m.role)
        lines.append(f"{label}: {m.content}")
    return "\n".join(lines)


@router.post("/{session_id}/message")
async def post_chat_message(session_id: str, body: ChatMessageRequest):
    """POST /api/v1/chat/{session_id}/message — SSE로 답변을 직접 스트리밍."""
    chat_history = _format_history(body.history)

    async def event_generator():
        try:
            async for event in run_chatbot(body.message, chat_history):
                yield _sse_format(event)
        except Exception as e:
            logger.exception("chat stream error: %s", e)
            yield _sse_format({"type": "error", "content": "응답 생성 중 오류가 발생했습니다."})
        finally:
            yield _sse_format({"type": "end", "content": ""})

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
async def delete_chat_history(session_id: str, user_id: str | None = None):
    """DELETE /api/v1/chat/{session_id}/history — 무상태라 실제 삭제 없음(클라이언트 호환용)."""
    return {"status": "deleted"}
