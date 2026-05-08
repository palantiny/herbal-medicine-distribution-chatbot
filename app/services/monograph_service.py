"""
모노그래프 서비스 — 약재명 → 모노그래프 dict 조회 + LLM3 프롬프트 블록 포맷팅.

모듈 로드 시 herb_monographs.json을 메모리에 캐시. 순수 함수.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_PATH = Path(__file__).parent.parent / "data" / "herb_monographs.json"
_DATA: dict[str, dict] = {}

try:
    with _PATH.open(encoding="utf-8") as f:
        _raw = json.load(f)
    _DATA = {k: v for k, v in _raw.items() if not k.startswith("_")}
    logger.info("herb_monographs.json loaded: %d entries", len(_DATA))
except Exception as e:
    logger.error("herb_monographs.json 로드 실패: %s", e)


def lookup(herb_name: str) -> dict | None:
    """정규화된 약재명으로 모노그래프 조회. 없으면 None."""
    if not herb_name:
        return None
    return _DATA.get(herb_name)


def lookup_for_herbs(herb_names: Iterable[str]) -> dict[str, dict]:
    """여러 약재명을 한 번에 조회. 매칭된 것만 dict로 반환."""
    out: dict[str, dict] = {}
    for name in herb_names:
        mono = lookup(name)
        if mono is not None:
            out[name] = mono
    return out


def format_for_prompt(mono: dict | None) -> str:
    """단일 모노그래프를 LLM3 프롬프트 블록으로 변환. 없으면 빈 문자열."""
    if not mono:
        return ""
    lines = [f"[참고: {mono.get('name_kr', '')} 모노그래프]"]
    if mono.get("name_latin"):
        lines.append(f"- 라틴명: {mono['name_latin']}")
    if mono.get("sungmi"):
        lines.append(f"- 성미: {mono['sungmi']}")
    if mono.get("guigyeong"):
        lines.append(f"- 귀경: {', '.join(mono['guigyeong'])}")
    if mono.get("hyoneung"):
        lines.append(f"- 효능: {', '.join(mono['hyoneung'])}")
    if mono.get("juchi"):
        lines.append(f"- 주치: {mono['juchi']}")
    if mono.get("yongryang"):
        lines.append(f"- 용량: {mono['yongryang']}")
    if mono.get("geumgi"):
        lines.append(f"- 금기: {mono['geumgi']}")
    if mono.get("chejil"):
        lines.append(f"- 체질배속: {mono['chejil']}")
    if mono.get("note"):
        lines.append(f"- 비고: {mono['note']}")
    return "\n".join(lines)


def format_many_for_prompt(monos: dict[str, dict]) -> str:
    """여러 모노그래프를 한 블록으로. 빈 dict면 빈 문자열."""
    if not monos:
        return ""
    parts = [format_for_prompt(m) for m in monos.values()]
    return "\n\n".join(p for p in parts if p)
