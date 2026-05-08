"""list_user_medicines + get_my_full_inventory intent 단위 테스트."""
from unittest.mock import patch
import pytest


# ── list_user_medicines (server1과 동일 패턴) ──────────────────────────────
@pytest.mark.asyncio
async def test_list_user_medicines_aggregates_member_results():
    """maker_list → medicine_by_maker → member_medicine 흐름이 합쳐지는지."""
    from app.services import djmedi_service

    djmedi_service._USER_HERBS_CACHE.clear()

    fake_makers = [{"mk_code": "0001", "mk_name": "A제약"}]
    fake_meds = [
        {"md_code": "M1", "md_medi": "MD1", "md_name": "감초"},
        {"md_code": "M2", "md_medi": "MD2", "md_name": "황기"},
    ]

    async def fake_get_maker_list():
        return fake_makers

    async def fake_get_medicine_by_maker(mk_code):
        return fake_meds

    async def fake_get_member_medicine(cfcode, md_medi):
        if md_medi == "MD1":
            return [{"md_code": "M1", "md_name": "감초", "mm_origin": "한국", "mk_name": "디제이허브"}]
        if md_medi == "MD2":
            return []  # 사용자 미보유
        return []

    with patch("app.services.djmedi_service.get_maker_list", side_effect=fake_get_maker_list), \
         patch("app.services.djmedi_service.get_medicine_by_maker", side_effect=fake_get_medicine_by_maker), \
         patch("app.services.djmedi_service.get_member_medicine", side_effect=fake_get_member_medicine):
        result = await djmedi_service.list_user_medicines("dj")

    assert len(result) == 1
    assert result[0]["md_code"] == "M1"
    assert result[0]["mm_origin"] == "한국"


@pytest.mark.asyncio
async def test_list_user_medicines_returns_empty_when_no_cfcode():
    from app.services.djmedi_service import list_user_medicines
    assert await list_user_medicines("") == []


@pytest.mark.asyncio
async def test_list_user_medicines_caches_per_cfcode():
    from app.services import djmedi_service

    djmedi_service._USER_HERBS_CACHE.clear()

    call_count = {"makers": 0, "members": 0}

    async def fake_get_maker_list():
        call_count["makers"] += 1
        return [{"mk_code": "0001", "mk_name": "A"}]

    async def fake_get_medicine_by_maker(mk_code):
        return [{"md_code": "M1", "md_medi": "MD1", "md_name": "감초"}]

    async def fake_get_member_medicine(cfcode, md_medi):
        call_count["members"] += 1
        return [{"md_code": "M1", "md_name": "감초", "mk_name": "X"}]

    with patch("app.services.djmedi_service.get_maker_list", side_effect=fake_get_maker_list), \
         patch("app.services.djmedi_service.get_medicine_by_maker", side_effect=fake_get_medicine_by_maker), \
         patch("app.services.djmedi_service.get_member_medicine", side_effect=fake_get_member_medicine):
        await djmedi_service.list_user_medicines("dj")
        await djmedi_service.list_user_medicines("dj")

    assert call_count["makers"] == 1
    assert call_count["members"] == 1


# ── smart_search get_my_full_inventory intent ──────────────────────────────
@pytest.mark.asyncio
async def test_smart_search_full_inventory_returns_user_meds():
    from app.services import djmedi_service

    djmedi_service._USER_HERBS_CACHE.clear()

    fake_user_meds = [
        {"md_code": "M1", "md_name": "감초", "mm_origin": "한국", "mk_name": "디제이허브"},
        {"md_code": "M2", "md_name": "황기", "mm_origin": "수입", "mk_name": "디제이허브"},
    ]

    async def fake_list_user_medicines(cfcode):
        assert cfcode == "dj"
        return fake_user_meds

    with patch("app.services.djmedi_service.list_user_medicines", side_effect=fake_list_user_medicines):
        api_code, items = await djmedi_service.smart_search(
            intent="get_my_full_inventory",
            cfcode="dj",
        )
    assert api_code == "membermedicine"
    assert len(items) == 2


@pytest.mark.asyncio
async def test_smart_search_full_inventory_filters_by_origin():
    """origin 파라미터로 결과 필터링."""
    from app.services import djmedi_service

    fake_user_meds = [
        {"md_code": "M1", "md_name": "감초", "mm_origin": "한국", "mk_name": "X"},
        {"md_code": "M2", "md_name": "황기", "mm_origin": "수입", "mk_name": "X"},
        {"md_code": "M3", "md_name": "당귀", "mm_origin": "한국", "mk_name": "X"},
    ]

    async def fake_list_user_medicines(cfcode):
        return fake_user_meds

    with patch("app.services.djmedi_service.list_user_medicines", side_effect=fake_list_user_medicines):
        _, items = await djmedi_service.smart_search(
            intent="get_my_full_inventory",
            cfcode="dj",
            origin="한국",
        )
    assert len(items) == 2
    names = {it["md_name"] for it in items}
    assert names == {"감초", "당귀"}


@pytest.mark.asyncio
async def test_smart_search_full_inventory_returns_empty_without_cfcode():
    """cfcode 없으면 빈 결과."""
    from app.services import djmedi_service

    api_code, items = await djmedi_service.smart_search(intent="get_my_full_inventory")
    assert api_code == "membermedicine"
    assert items == []
