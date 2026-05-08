"""_step_llm2 라우팅 단위 테스트 — OpenAI 호출 mock."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_llm2_returns_knowledge_first_for_general_question():
    from app.services.pipeline import Llm2Output, _step_llm2
    from app.services.scheme_resolver import SqlHint

    fake_parsed = Llm2Output(mode="KNOWLEDGE_FIRST", reason="일반 한의학 지식")
    fake_choice = MagicMock()
    fake_choice.message.parsed = fake_parsed
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    with patch(
        "app.services.pipeline._get_client",
        return_value=MagicMock(
            beta=MagicMock(
                chat=MagicMock(
                    completions=MagicMock(parse=AsyncMock(return_value=fake_response))
                )
            )
        ),
    ):
        out = await _step_llm2(
            question="감초 효능이 뭐야?",
            chat_history="(이전 대화 없음)",
            extraction=None,
            hint=SqlHint(),
            cfcode=None,
        )
    assert out.mode == "KNOWLEDGE_FIRST"


@pytest.mark.asyncio
async def test_llm2_fallback_when_parse_fails():
    from app.services.pipeline import _step_llm2
    from app.services.scheme_resolver import SqlHint

    with patch(
        "app.services.pipeline._get_client",
        return_value=MagicMock(
            beta=MagicMock(
                chat=MagicMock(
                    completions=MagicMock(parse=AsyncMock(side_effect=RuntimeError("api fail")))
                )
            )
        ),
    ):
        out = await _step_llm2(
            question="아무 질문",
            chat_history="(이전 대화 없음)",
            extraction=None,
            hint=SqlHint(),
            cfcode=None,
        )
    assert out.mode == "KNOWLEDGE_FIRST"
    assert "fallback" in (out.reason or "").lower()
