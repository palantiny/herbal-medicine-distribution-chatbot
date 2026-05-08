"""_step_post_cards 단위 테스트 — Redis publish 모킹."""
from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest


@pytest.mark.asyncio
async def test_db_first_emits_one_card_per_item():
    from app.services.pipeline import Llm2Output, _step_post_cards

    parsed = Llm2Output(mode="DB_FIRST", reason="test")
    items = [
        {"md_code": "M1", "md_name": "감초", "mk_name": "씨케이"},
        {"md_code": "M2", "md_name": "당귀", "mk_name": "광명당"},
    ]
    redis = MagicMock()
    redis.publish = AsyncMock()

    await _step_post_cards(parsed, "answer text", items, None, redis, "ch")

    assert redis.publish.await_count == 2
    payloads = [json.loads(call.args[1]) for call in redis.publish.await_args_list]
    assert payloads[0]["type"] == "herb_card"
    assert payloads[0]["herb_name"] == "감초"
    assert payloads[0]["data"]["md_code"] == "M1"
    assert payloads[1]["herb_name"] == "당귀"


@pytest.mark.asyncio
async def test_db_first_skips_notice_items():
    from app.services.pipeline import Llm2Output, _step_post_cards

    parsed = Llm2Output(mode="DB_FIRST", reason="test")
    items = [
        {"md_code": "M1", "md_name": "감초"},
    ]
    redis = MagicMock()
    redis.publish = AsyncMock()

    await _step_post_cards(parsed, "", items, None, redis, "ch")

    assert redis.publish.await_count == 1


@pytest.mark.asyncio
async def test_knowledge_first_calls_my_medicines_when_cfcode_present():
    from app.services.pipeline import Llm2Output, _step_post_cards

    parsed = Llm2Output(mode="KNOWLEDGE_FIRST", reason="test")
    redis = MagicMock()
    redis.publish = AsyncMock()

    smart_search_mock = AsyncMock(return_value=("membermedicine", [
        {"md_code": "M1", "md_name": "감초", "mm_origin": "한국"}
    ]))

    with patch("app.services.pipeline.extract_mentioned_herbs", AsyncMock(return_value=["감초"])):
        with patch("app.services.pipeline.smart_search", smart_search_mock):
            await _step_post_cards(parsed, "감초가 좋습니다", [], "dj", redis, "ch")

    assert smart_search_mock.await_count == 1
    args = smart_search_mock.await_args
    assert args.kwargs["intent"] == "get_my_medicines"
    assert args.kwargs["cfcode"] == "dj"
    assert redis.publish.await_count == 1


@pytest.mark.asyncio
async def test_knowledge_first_falls_back_to_get_herb_by_name_without_cfcode():
    from app.services.pipeline import Llm2Output, _step_post_cards

    parsed = Llm2Output(mode="KNOWLEDGE_FIRST", reason="test")
    redis = MagicMock()
    redis.publish = AsyncMock()

    smart_search_mock = AsyncMock(return_value=("herbmedicine", [
        {"md_code": "M1", "md_name": "감초"}
    ]))

    with patch("app.services.pipeline.extract_mentioned_herbs", AsyncMock(return_value=["감초"])):
        with patch("app.services.pipeline.smart_search", smart_search_mock):
            await _step_post_cards(parsed, "감초", [], None, redis, "ch")

    assert smart_search_mock.await_count == 1
    assert smart_search_mock.await_args.kwargs["intent"] == "get_herb_by_name"


@pytest.mark.asyncio
async def test_sql_mode_emits_no_cards():
    from app.services.pipeline import Llm2Output, _step_post_cards

    parsed = Llm2Output(mode="SQL", reason="test")
    redis = MagicMock()
    redis.publish = AsyncMock()

    await _step_post_cards(parsed, "answer", [{"md_code": "M1"}], None, redis, "ch")

    assert redis.publish.await_count == 0
