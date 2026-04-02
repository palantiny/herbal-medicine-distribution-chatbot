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
from app.services.graph_service import close_neo4j

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await get_redis()

    boto_session = aioboto3.Session()
    app.state.chat_repo = DynamoDBChatHistoryRepository(boto_session)
    logger.info("Chatbot server started")
    yield

    await close_neo4j()
    await close_redis()
    await close_db()
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
