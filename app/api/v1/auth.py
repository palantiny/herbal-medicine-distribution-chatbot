"""
인증 API: POST /api/v1/auth/verify
파트너사 partner_token 검증 후 session_id, cfcode 및 최근 대화 기록(DynamoDB) 반환.
클라이언트는 응답의 cfcode를 저장해 이후 chat 요청 body에 포함해야 함.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import verify_partner_token_format
from app.models import User
from app.utils.helpers import generate_session_id
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class VerifyRequest(BaseModel):
    """인증 요청 Body."""

    partner_token: str


class VerifyResponse(BaseModel):
    """인증 응답."""

    session_id: str
    user_id: str
    cfcode: str | None
    recent_history: list[dict]


@router.post("/verify", response_model=VerifyResponse)
async def verify_partner(
    body: VerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    """
    partner_token 검증 및 세션 초기화.
    1. 토큰으로 User 조회 (PostgreSQL)
    2. ChatHistory에서 최근 대화 로드 (DynamoDB)
    3. 새 session_id + cfcode 반환
    """
    if not verify_partner_token_format(body.partner_token):
        raise HTTPException(status_code=401, detail="Invalid partner_token")

    result = await db.execute(
        select(User).where(User.partner_token == body.partner_token.strip())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    chat_repo = getattr(request.app.state, "chat_repo", None)
    if chat_repo:
        recent_history = await chat_repo.get_recent(
            user_id=str(user.user_id),
            session_id="",
            limit=20,
        )
    else:
        recent_history = []

    session_id = generate_session_id(user.user_id)

    return VerifyResponse(
        session_id=session_id,
        user_id=str(user.user_id),
        cfcode=user.cfcode,
        recent_history=recent_history,
    )
