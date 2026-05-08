"""
Palantiny 설정 모듈
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 데이터베이스
    DATABASE_URL: str = "postgresql+asyncpg://palantiny:palantiny_secret@localhost:5432/palantiny_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # OpenAI
    OPENAI_API_KEY: str = ""

    # 앱
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Redis Queue 키
    SQL_TASK_QUEUE: str = "sql_task_queue"
    SQL_RESULT_PREFIX: str = "sql_result:"
    SQL_RESULT_TTL: int = 60

    # Redis Chat MQ
    CHAT_TASK_QUEUE: str = "chat_task_queue"
    CHAT_STREAM_PREFIX: str = "chat:stream:"

    # DynamoDB
    AWS_REGION_NAME: str = "ap-northeast-2"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    DYNAMODB_TABLE_CHAT: str = "palantiny-chat-history"

    # CORS
    ALLOWED_ORIGINS: str = "*"

    # DJMEDI 약재 연동 API
    DJMEDI_API_BASE_URL: str = "https://devapi.djmedi.net/djherb/"
    DJMEDI_AUTH_KEY: str = "HERBfHShheT88iuYgNaDvDwgF9X5kBrJ"

    # Context 제한
    CONTEXT_MAX_TOKENS: int = 120_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
