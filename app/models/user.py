"""
User 모델 - 파트너사별 사용자
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    """파트너사 웹사이트에서 partner_token으로 식별되는 사용자."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    partner_token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # DJMEDI 업체코드 — membermedicine API 호출 시 사용 (예: "dj", "hs", "ch")
    cfcode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    # 관계
    chat_histories = relationship("ChatHistory", back_populates="user")
