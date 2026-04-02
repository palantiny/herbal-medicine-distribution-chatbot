"""
ChatHistory Repository - DynamoDB
채팅 히스토리 저장/조회를 담당. aioboto3 기반 비동기 처리.
"""
from datetime import datetime, timezone
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


class DynamoDBChatHistoryRepository:
    """DynamoDB 기반 채팅 히스토리 저장소.

    Table schema:
        PK: session_id (S)
        SK: created_at (S, ISO 8601)
        GSI: user_id-created_at-index
            PK: user_id (S)
            SK: created_at (S)
    """

    def __init__(self, session):
        """aioboto3 Session 주입."""
        self._session = session
        self._table_name = settings.DYNAMODB_TABLE_CHAT
        self._region = settings.AWS_REGION_NAME

    def _client_kwargs(self) -> dict:
        kwargs = {"region_name": self._region}
        # EC2 IAM Role 사용 시 키 불필요. 명시적 키가 있을 때만 전달.
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        return kwargs

    async def get_recent(self, _user_id: str, session_id: str, limit: int = 20) -> list[dict]:
        """session_id 기준으로 최근 대화 조회. 과거→최신 순 반환."""
        async with self._session.resource("dynamodb", **self._client_kwargs()) as dynamodb:
            table = await dynamodb.Table(self._table_name)
            response = await table.query(
                KeyConditionExpression="session_id = :sid",
                ExpressionAttributeValues={":sid": session_id},
                ScanIndexForward=False,  # created_at 내림차순
                Limit=limit,
            )
        items = response.get("Items", [])
        items.reverse()  # 과거→최신 순으로 변환
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in items]

    async def get_recent_by_user(self, user_id: str, limit: int = 20) -> list[dict]:
        """user_id GSI 기준으로 최근 대화 조회 (로그인 시 이전 대화 복원용)."""
        async with self._session.resource("dynamodb", **self._client_kwargs()) as dynamodb:
            table = await dynamodb.Table(self._table_name)
            response = await table.query(
                IndexName="user_id-created_at-index",
                KeyConditionExpression="user_id = :uid",
                ExpressionAttributeValues={":uid": user_id},
                ScanIndexForward=False,
                Limit=limit,
            )
        items = response.get("Items", [])
        items.reverse()
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in items]

    async def save(self, session_id: str, user_id: str, role: str, content: str) -> None:
        """대화 한 턴 저장."""
        created_at = datetime.now(timezone.utc).isoformat()
        async with self._session.resource("dynamodb", **self._client_kwargs()) as dynamodb:
            table = await dynamodb.Table(self._table_name)
            await table.put_item(
                Item={
                    "session_id": session_id,
                    "created_at": created_at,
                    "user_id": user_id,
                    "role": role,
                    "content": content,
                }
            )

    async def clear_history(self, session_id: str, _user_id: str) -> None:
        """session_id에 해당하는 대화 기록 전체 삭제."""
        async with self._session.resource("dynamodb", **self._client_kwargs()) as dynamodb:
            table = await dynamodb.Table(self._table_name)
            response = await table.query(
                KeyConditionExpression="session_id = :sid",
                ExpressionAttributeValues={":sid": session_id},
            )
            async with table.batch_writer() as batch:
                for item in response.get("Items", []):
                    await batch.delete_item(
                        Key={"session_id": item["session_id"], "created_at": item["created_at"]}
                    )
