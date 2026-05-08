"""
Scheme Resolver — BM25 기반 엔티티 → SQL Hint 변환

모듈 로드 시 scheme_aliases.json을 읽어 슬롯별 BM25 인덱스를 메모리에 빌드.
resolve_entities()는 동기 함수(in-process, 수 마이크로초). Redis 캐시 불필요.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.services.entity_extractor import ExtractedEntity

logger = logging.getLogger(__name__)

# ── JSON 로드 ─────────────────────────────────────────────────────────────────
_ALIASES_PATH = Path(__file__).parent.parent / "data" / "scheme_aliases.json"
_ALIASES: dict[str, list[dict]] = {}

try:
    with _ALIASES_PATH.open(encoding="utf-8") as f:
        _raw = json.load(f)
    _ALIASES = {k: v for k, v in _raw.items() if not k.startswith("_")}
    logger.info("scheme_aliases.json loaded: %s slots", list(_ALIASES.keys()))
except Exception as e:
    logger.error("scheme_aliases.json 로드 실패: %s", e)


# ── Pydantic 모델 ──────────────────────────────────────────────────────────────
class ColumnHint(BaseModel):
    slot: str           # maker / origin / herb / packaging_unit
    table: str          # 검색 대상 테이블
    column: str         # 검색 컬럼명
    value: str          # DB에 저장된 실제 값 (정규화됨)
    matched_alias: str  # BM25로 매칭된 입력 표현
    score: float        # BM25 점수 (0 이상)


class SqlHint(BaseModel):
    hints: list[ColumnHint] = []
    tables: list[str] = []   # 등장 테이블 dedup (JOIN 결정에 활용)

    def is_empty(self) -> bool:
        return len(self.hints) == 0


# ── 토크나이저 ─────────────────────────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    """
    한글+영문 혼용 토크나이저.
    공백 분리 토큰을 기본으로 하되, 4자 이상 한글 시퀀스에만 bigram 추가.
    3자 이하(예: '중국산')는 bigram 없이 공백 분리 토큰만 사용.
    → '중국산' bigram인 '국산'이 한국 alias에 오매칭하는 문제 방지.
    """
    text = text.strip().lower()
    tokens = re.split(r"\s+", text)
    extra: list[str] = []
    for tok in tokens:
        korean = re.sub(r"[^\uAC00-\uD7A3]", "", tok)
        if len(korean) >= 4:           # 4자 이상에만 bigram
            for i in range(len(korean) - 1):
                extra.append(korean[i : i + 2])
    return [t for t in tokens + extra if t]


# ── BM25 인덱스 빌드 ──────────────────────────────────────────────────────────
class _BM25Corpus:
    """슬롯 하나에 대한 BM25 인덱스 + 원본 객체 참조."""

    def __init__(self, entries: list[dict]) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            raise ImportError("rank-bm25 패키지가 필요합니다: pip install rank-bm25")

        # alias 하나 = corpus 문서 1개. 같은 entry가 여러 alias를 가지면 복수 등록.
        self.docs: list[str] = []          # 각 문서의 원문 alias
        self.entry_refs: list[dict] = []   # alias → 원본 entry 역참조

        tokenized_corpus: list[list[str]] = []
        for entry in entries:
            for alias in entry.get("aliases", []):
                self.docs.append(alias)
                self.entry_refs.append(entry)
                tokenized_corpus.append(_tokenize(alias))

        if tokenized_corpus:
            self.bm25 = BM25Okapi(tokenized_corpus)
        else:
            self.bm25 = None

    def search(self, query: str, top_k: int = 3) -> list[tuple[dict, str, float]]:
        """
        Returns list of (entry, matched_alias, score), sorted by score desc.
        """
        if self.bm25 is None:
            return []
        q_tokens = _tokenize(query)
        scores = self.bm25.get_scores(q_tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results: list[tuple[dict, str, float]] = []
        seen_values: set[str] = set()
        for idx, score in ranked[:top_k * 3]:  # 넉넉히 가져와서 dedup
            if score <= 0.0:
                break
            entry = self.entry_refs[idx]
            alias = self.docs[idx]
            dedup_key = f"{entry['table']}::{entry['column']}::{entry['value']}"
            if dedup_key not in seen_values:
                seen_values.add(dedup_key)
                results.append((entry, alias, float(score)))
            if len(results) >= top_k:
                break
        return results


# 슬롯별 BM25 인덱스 (모듈 로드 시 1회 빌드)
_INDICES: dict[str, _BM25Corpus] = {}
for _slot, _entries in _ALIASES.items():
    try:
        _INDICES[_slot] = _BM25Corpus(_entries)
        logger.info("BM25 index built: slot=%s, docs=%d", _slot, len(_INDICES[_slot].docs))
    except Exception as _e:
        logger.error("BM25 index build failed for slot=%s: %s", _slot, _e)

# slot 별칭 (entity_extractor가 반환하는 slot 이름 → aliases.json 슬롯 키)
_SLOT_ALIAS_MAP: dict[str, str] = {
    "maker": "makers",
    "makers": "makers",
    "origin": "origins",
    "origins": "origins",
    "herb_name": "herbs",
    "herb": "herbs",
    "herbs": "herbs",
    "packaging_unit": "packaging_units",
    "packaging_units": "packaging_units",
}


# ── 공개 API ──────────────────────────────────────────────────────────────────
def resolve_entities(
    entities: list["ExtractedEntity"],
    top_k: int = 2,
    threshold: float = 0.5,  # Fix #8: 0.0 → 0.5 (약한 매칭 차단)
) -> SqlHint:
    """
    LLM1이 추출한 엔티티 목록을 받아 ColumnHint 목록으로 변환.

    Parameters
    ----------
    entities:  LLM1 출력의 ExtractedEntity 리스트
    top_k:     슬롯당 반환 최대 항목 수
    threshold: BM25 점수 최소 임계값 (0.0 → 양수면 모두 통과)

    Returns
    -------
    SqlHint: hints(매핑된 컬럼/테이블/값), tables(중복 제거 테이블 목록)
    """
    hints: list[ColumnHint] = []
    seen_hints: set[str] = set()

    for entity in entities:
        slot_key = _SLOT_ALIAS_MAP.get(entity.slot)
        if not slot_key or slot_key not in _INDICES:
            logger.debug("Unknown slot '%s', skipping BM25 lookup", entity.slot)
            continue

        corpus = _INDICES[slot_key]
        results = corpus.search(entity.surface, top_k=top_k)

        for entry, matched_alias, score in results:
            if score < threshold:
                continue
            dedup_key = f"{entry['table']}::{entry['column']}::{entry['value']}"
            if dedup_key in seen_hints:
                continue
            seen_hints.add(dedup_key)
            hints.append(
                ColumnHint(
                    slot=entity.slot,
                    table=entry["table"],
                    column=entry["column"],
                    value=entry["value"],
                    matched_alias=matched_alias,
                    score=score,
                )
            )
            logger.debug(
                "Resolved: slot=%s surface=%r → %s.%s='%s' (score=%.3f)",
                entity.slot, entity.surface,
                entry["table"], entry["column"], entry["value"], score,
            )

    tables = list(dict.fromkeys(h.table for h in hints))  # 순서 보존 dedup
    return SqlHint(hints=hints, tables=tables)


def format_hints_for_prompt(hint: SqlHint) -> str:
    """
    SqlHint를 LLM2 프롬프트에 삽입할 텍스트 블록으로 변환.
    table='djmedi'인 항목은 DJMEDI API 파라미터로,
    table='sql'인 항목은 SQL WHERE 조건으로 분리해서 표시.
    """
    if hint.is_empty():
        return "(엔티티 매핑 없음)"

    djmedi_lines: list[str] = []
    sql_lines: list[str] = []

    for h in hint.hints:
        label = f"  • {h.column} = '{h.value}'  (입력: '{h.matched_alias}')"
        if h.table == "djmedi":
            djmedi_lines.append(label)
        else:
            sql_lines.append(f"  • {h.table}.{h.column} = '{h.value}'  (입력: '{h.matched_alias}')")

    sections: list[str] = []
    if djmedi_lines:
        sections.append("[DJMEDI API 파라미터 (정규화된 값)]")
        sections.extend(djmedi_lines)
    if sql_lines:
        sections.append("[SQL WHERE 조건 (로컬 DB 전용)]")
        sections.extend(sql_lines)

    return "\n".join(sections)
