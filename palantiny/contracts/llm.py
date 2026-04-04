from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class FallbackNotice:
    mode: Literal["general_knowledge", "graph_only", "sql_only", "none"]
    message: str


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant", "system"]
    content: str
    created_at_iso: Optional[str] = None
