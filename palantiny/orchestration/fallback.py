"""Vector-miss / empty-context messaging (reserved for future GraphRAG router)."""

from palantiny.contracts.llm import FallbackNotice

WARN_GENERAL_KNOWLEDGE = (
    "지식 그래프와 DB에서 직접적인 근거를 찾지 못했습니다. 일반 지식 범위에서 답변합니다."
)


def general_knowledge_fallback() -> FallbackNotice:
    return FallbackNotice(mode="general_knowledge", message=WARN_GENERAL_KNOWLEDGE)
