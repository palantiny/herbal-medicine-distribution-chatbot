"""
Protocol aligned with app.repositories.chat_history_repository.MongoChatHistoryRepository.

The FastAPI app owns persistence; Palantiny modules must not open a second store by default.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChatHistoryRepositoryProtocol(Protocol):
    async def get_recent(self, user_id: str, session_id: str, limit: int = 20) -> list[dict]: ...

    async def save(self, session_id: str, user_id: str, role: str, content: str) -> None: ...

    async def close(self) -> Any: ...
