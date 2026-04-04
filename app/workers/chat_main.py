"""
Standalone Entrypoint for Chat Worker
"""
import asyncio
import logging

from app.core.database import close_db, close_redis, get_redis, init_db
from app.repositories.chat_history_repository import MongoChatHistoryRepository
from app.services.chat_worker import run_chat_worker
from app.services.graph_service import close_neo4j

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Chat Worker starting initialized")
    await init_db()
    redis = await get_redis()
    chat_repo = MongoChatHistoryRepository()
    
    try:
        await run_chat_worker(redis, chat_repo)
    except asyncio.CancelledError:
        logger.info("Chat Worker Cancelled")
    except Exception as e:
        logger.exception(f"Chat Worker crashed: {e}")
    finally:
        if hasattr(chat_repo, "close"):
            close_fn = chat_repo.close
            if asyncio.iscoroutinefunction(close_fn):
                await close_fn()
            else:
                close_fn()
        await close_neo4j()
        await close_redis()
        await close_db()
        logger.info("Chat Worker shutdown sequentially complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Chat Worker Terminated by user.")
