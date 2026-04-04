"""Thin OpenAI wrapper stub; production uses app.services.pipeline._call_llm_text."""


async def chat_completion_text_stub(system: str, user: str, api_key: str | None = None) -> str:
    raise NotImplementedError("Use app pipeline OpenAI client.")
