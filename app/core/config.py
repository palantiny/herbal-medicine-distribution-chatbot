"""
Palantiny 설정 모듈
Pydantic Settings를 사용하여 환경 변수 기반 설정 관리.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정. .env 파일 및 환경 변수에서 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 데이터베이스
    DATABASE_URL: str = "postgresql+asyncpg://palantiny:palantiny_secret@localhost:5432/palantiny_db"

    # Redis (Queue 및 Pub/Sub용)
    REDIS_URL: str = "redis://localhost:6379/0"

    # OpenAI API
    OPENAI_API_KEY: str = ""

    # 앱 환경
    APP_ENV: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    # Redis Queue 키 (DB 락 방지를 위한 비동기 SQL 실행용)
    SQL_TASK_QUEUE: str = "sql_task_queue"
    SQL_RESULT_PREFIX: str = "sql_result:"
    SQL_RESULT_TTL: int = 60  # 초

    # Redis Queue/Pub/Sub 키 (Chat MQ 아키텍처용)
    CHAT_TASK_QUEUE: str = "chat_task_queue"
    CHAT_STREAM_PREFIX: str = "chat:stream:"

    # DynamoDB (ChatHistory)
    AWS_REGION_NAME: str = "ap-northeast-2"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    DYNAMODB_TABLE_CHAT: str = "palantiny-chat-history"

    # CORS
    ALLOWED_ORIGINS: str = "*"

    # Neo4j (한약재 지식 그래프)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "palantiny_secret"
    NEO4J_DATABASE: str = "neo4j"

    # 128k context 제한 (토큰 단위)
    CONTEXT_MAX_TOKENS: int = 120_000


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤. lru_cache로 한 번만 로드."""
    return Settings()
