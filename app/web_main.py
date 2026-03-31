"""
Palantiny Web Server - FastAPI 진입점
herbs API만 담당. PostgreSQL만 사용.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import herbs
from app.core.database import close_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Web server started")
    yield
    await close_db()
    logger.info("Web server stopped")


app = FastAPI(
    title="Palantiny Web API",
    description="한약재 유통 웹사이트 서버",
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

app.include_router(herbs.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "server": "web"}
