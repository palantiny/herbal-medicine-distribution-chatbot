"""Pipeline memory is a formatted string from Mongo (get_context_within_limit); optional helpers."""

from palantiny.contracts.llm import ChatTurn


def format_history_for_prompt(turns: list[ChatTurn]) -> str:
    """Format structured turns into the same style history_manager uses (plain text)."""
    parts: list[str] = []
    for t in turns:
        label = {"user": "사용자", "assistant": "어시스턴트", "system": "시스템"}[t.role]
        parts.append(f"{label}: {t.content}")
    return "\n".join(parts)
