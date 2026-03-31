"""
ChatHistory Repository - MongoDB + Memory Mock
채팅 히스토리 저장/조회를 추상화. MongoDB 또는 메모리로 전환 가능.
"""
from datetime import datetime
from typing import Protocol

from app.core.config import get_settings

settings = get_settings()


class ChatHistoryRepository(Protocol):
    """채팅 히스토리 저장소 프로토콜."""

    async def get_recent(self, user_id: str, session_id: str, limit: int = 20) -> list[dict]:
        """최근 대화를 과거→최신 순으로 반환."""
        ...

    async def save(self, session_id: str, user_id: str, role: str, content: str) -> None:
        """대화 한 턴 저장."""
        ...

    async def clear_history(self, session_id: str, user_id: str) -> None:
        """대화 기록 삭제."""
        ...


class MongoChatHistoryRepository:
    """MongoDB 기반 채팅 히스토리 저장소."""

    def __init__(self):
        self._client = None
        self._db = None
        self._collection: str = "chat_histories"

    async def _ensure_connected(self):
        if self._client is None:
            from motor.motor_asyncio import AsyncIOMotorClient

            self._client = AsyncIOMotorClient(settings.MONGODB_URI)
            self._db = self._client[settings.MONGODB_DB]
            # 인덱스 생성
            await self._db[self._collection].create_index([("user_id", 1), ("created_at", -1)])
            await self._db[self._collection].create_index([("session_id", 1), ("created_at", -1)])

    async def get_recent(self, user_id: str, session_id: str, limit: int = 20) -> list[dict]:
        await self._ensure_connected()
        cursor = (
            self._db[self._collection]
            .find({"$or": [{"user_id": user_id}, {"session_id": session_id}]})
            .sort("created_at", -1)
            .limit(limit)
        )
        rows = await cursor.to_list(length=limit)
        # 과거→최신 순으로 변환
        rows.reverse()
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"].isoformat()} for r in rows]

    async def save(self, session_id: str, user_id: str, role: str, content: str) -> None:
        await self._ensure_connected()
        await self._db[self._collection].insert_one(
            {
                "session_id": session_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "created_at": datetime.utcnow(),
            }
        )

    async def clear_history(self, session_id: str, user_id: str) -> None:
        await self._ensure_connected()
        query = {"user_id": user_id} if user_id else {"session_id": session_id}
        await self._db[self._collection].delete_many(query)

    async def close(self):
        if self._client:
            self._client.close()
            self._client = None
            self._db = None


