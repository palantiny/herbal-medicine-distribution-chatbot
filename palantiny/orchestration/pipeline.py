"""Optional offline pipeline assembly (server uses app.services.pipeline)."""

from typing import Any


async def run_turn_stub(chat_history: str, question: str, **kwargs: Any) -> str:
    raise NotImplementedError("Use FastAPI chat_worker + run_pipeline for production.")
