"""
Standalone Entrypoint for SQL Worker
"""
import asyncio
import logging

from app.core.database import close_db, close_redis, get_redis, init_db
from app.services.sql_worker import run_sql_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("SQL Worker starting initialized")
    await init_db()
    redis = await get_redis()
    
    try:
        await run_sql_worker(redis)
    except asyncio.CancelledError:
        logger.info("SQL Worker Cancelled")
    except Exception as e:
        logger.exception(f"SQL Worker crashed: {e}")
    finally:
        await close_redis()
        await close_db()
        logger.info("SQL Worker shutdown sequentially complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SQL Worker Terminated by user.")
