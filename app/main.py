"""
Palantiny Chatbot Server - FastAPI 진입점
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, cache, chat, herbs
from app.core.config import get_settings
from app.core.database import close_db, close_redis, get_redis, init_db
from app.repositories.chat_history_repository import MongoChatHistoryRepository
from app.services.graph_service import close_neo4j

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB/Redis/MongoDB 초기화, chat_repo 설정. 종료 시 정리."""
    # Startup
    await init_db()
    redis = await get_redis()

    # ChatHistory Repository (MongoDB)
    app.state.chat_repo = MongoChatHistoryRepository()
    logger.info("Using MongoChatHistoryRepository")

    logger.info("Palantiny server started")
    yield
    # Shutdown
    chat_repo = getattr(app.state, "chat_repo", None)
    if chat_repo and hasattr(chat_repo, "close"):
        close_fn = chat_repo.close
        if asyncio.iscoroutinefunction(close_fn):
            await close_fn()
        else:
            close_fn()
    await close_neo4j()
    await close_redis()
    await close_db()
    logger.info("Palantiny server stopped")


app = FastAPI(
    title="Palantiny Chatbot API",
    description="한약재 유통 B2B2C 챗봇 서버",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 라우터
app.include_router(auth.router, prefix="/api/v1")
app.include_router(cache.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(herbs.router, prefix="/api/v1")


@app.get("/health")
async def health():
    """헬스 체크."""
    return {"status": "ok"}
