"""
Palantiny Chatbot Server - FastAPI 진입점
chat / auth / cache API만 담당.
"""
import logging
from contextlib import asynccontextmanager

import aioboto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, cache, chat
from app.core.config import get_settings
from app.core.database import close_db, close_redis, get_redis, init_db
from app.repositories.chat_history_repository import DynamoDBChatHistoryRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 더미데이터 모드: PostgreSQL/Redis/DynamoDB는 선택적 의존성.
    # 초기화에 실패해도 OpenAI 기반 챗봇(chat 라우터)은 정상 동작한다.
    app.state.chat_repo = None
    try:
        await init_db()
        await get_redis()
        boto_session = aioboto3.Session()
        app.state.chat_repo = DynamoDBChatHistoryRepository(boto_session)
    except Exception as e:
        logger.warning("인프라 초기화 일부 실패 — 더미 모드로 계속 진행: %s", e)
    logger.info("Chatbot server started")
    yield

    try:
        await close_redis()
        await close_db()
    except Exception:
        pass
    logger.info("Chatbot server stopped")


app = FastAPI(
    title="Palantiny Chatbot API",
    description="한약재 유통 챗봇 서버",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(cache.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "server": "chatbot"}
