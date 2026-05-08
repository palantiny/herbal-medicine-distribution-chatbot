"""monograph_service 단위 테스트."""
import pytest


def test_lookup_returns_none_when_unknown():
    from app.services.monograph_service import lookup
    assert lookup("듣도보도못한약재") is None


def test_lookup_returns_dict_for_known_herb():
    from app.services.monograph_service import lookup
    result = lookup("감초")
    assert result is not None
    assert result["name_kr"] == "감초"
    assert result.get("sungmi", "")  # 빈 문자열 아님
    assert isinstance(result.get("hyoneung", []), list)


def test_format_for_prompt_includes_key_fields():
    from app.services.monograph_service import format_for_prompt, lookup
    mono = lookup("감초")
    text = format_for_prompt(mono)
    assert "감초" in text
    assert "성미" in text
    assert "귀경" in text
    assert "효능" in text


def test_format_for_prompt_handles_none():
    from app.services.monograph_service import format_for_prompt
    assert format_for_prompt(None) == ""


def test_lookup_for_herbs_returns_dict_keyed_by_name():
    from app.services.monograph_service import lookup_for_herbs
    out = lookup_for_herbs(["감초", "없는약재", "당귀"])
    assert "감초" in out
    assert "당귀" in out
    assert "없는약재" not in out
    assert len(out) == 2
