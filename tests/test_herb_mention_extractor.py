"""herb_mention_extractor 단위 테스트 — OpenAI 호출은 mock."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_extract_returns_normalized_names():
    from app.services.herb_mention_extractor import (
        MentionedHerbs,
        extract_mentioned_herbs,
    )

    fake_parsed = MentionedHerbs(herbs=["감초", "당귀"])
    fake_choice = MagicMock()
    fake_choice.message.parsed = fake_parsed
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    with patch(
        "app.services.herb_mention_extractor._get_client",
        return_value=MagicMock(
            beta=MagicMock(
                chat=MagicMock(
                    completions=MagicMock(parse=AsyncMock(return_value=fake_response))
                )
            )
        ),
    ):
        out = await extract_mentioned_herbs("감초와 당귀를 함께 사용하면...")
    assert out == ["감초", "당귀"]


@pytest.mark.asyncio
async def test_extract_returns_empty_on_exception():
    from app.services.herb_mention_extractor import extract_mentioned_herbs

    with patch(
        "app.services.herb_mention_extractor._get_client",
        return_value=MagicMock(
            beta=MagicMock(
                chat=MagicMock(
                    completions=MagicMock(parse=AsyncMock(side_effect=RuntimeError("fail")))
                )
            )
        ),
    ):
        out = await extract_mentioned_herbs("감초")
    assert out == []


@pytest.mark.asyncio
async def test_extract_returns_empty_when_parsed_none():
    from app.services.herb_mention_extractor import extract_mentioned_herbs

    fake_choice = MagicMock()
    fake_choice.message.parsed = None
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    with patch(
        "app.services.herb_mention_extractor._get_client",
        return_value=MagicMock(
            beta=MagicMock(
                chat=MagicMock(
                    completions=MagicMock(parse=AsyncMock(return_value=fake_response))
                )
            )
        ),
    ):
        out = await extract_mentioned_herbs("감초")
    assert out == []
