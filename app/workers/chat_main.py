"""
Standalone Entrypoint for Chat Worker
"""
import asyncio
import logging

import aioboto3

from app.core.database import close_db, close_redis, get_redis, init_db
from app.repositories.chat_history_repository import DynamoDBChatHistoryRepository
from app.services.chat_worker import run_chat_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Chat Worker starting initialized")
    await init_db()
    redis = await get_redis()
    boto_session = aioboto3.Session()
    chat_repo = DynamoDBChatHistoryRepository(boto_session)

    try:
        await run_chat_worker(redis, chat_repo)
    except asyncio.CancelledError:
        logger.info("Chat Worker Cancelled")
    except Exception as e:
        logger.exception(f"Chat Worker crashed: {e}")
    finally:
        await close_redis()
        await close_db()
        logger.info("Chat Worker shutdown sequentially complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Chat Worker Terminated by user.")
