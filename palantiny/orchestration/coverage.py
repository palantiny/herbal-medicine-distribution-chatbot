"""
LLM-facing coverage notices: graph vs Postgres/cache (B/C) aligned with Palantiny plan.

Heuristics match `app.services.graph_service` Korean strings and SQL/cache blobs from pipeline.
"""

from __future__ import annotations

import json
import re

from palantiny.contracts.coverage import CoverageCase, CoverageNotice

WARN_GRAPH_ONLY_NO_DB = (
    "[시스템 안내] PostgreSQL·캐시(가격·재고 등 정형 DB)에서 해당 한약재에 대한 "
    "조회 결과가 없거나 비어 있습니다. 아래 답변은 지식 그래프(모노그래프) 및 제공된 "
    "문맥에만 근거합니다. 가격·재고가 필요하면 DB에 데이터가 있는지 확인해 주세요."
)

WARN_DB_ONLY_NO_GRAPH = (
    "[시스템 안내] 지식 그래프(Neo4j)에서 해당 한약재의 상세 온톨로지(효능·경락 등)를 "
    "찾지 못했습니다. 아래는 PostgreSQL/캐시 조회 결과 위주입니다. 그래프에 스텁 노드가 "
    "있는 경우 모노그래프 본문은 없을 수 있습니다."
)

WARN_STAGE2_GRAPH_PATH = (
    "[시스템 안내] 본 턴에서는 지식 그래프만 조회했으며 PostgreSQL 가격·재고 테이블은 "
    "조회하지 않았습니다. 단가·재고가 필요하면 다시 질문해 주세요."
)


def _graph_context_is_missing(graph_context: str) -> bool:
    t = (graph_context or "").strip()
    if not t:
        return True
    if "정보가 없습니다" in t:
        return True
    if "찾지 못했습니다" in t and "한약재:" not in t:
        return True
    if t.startswith("등록된 한약재:"):
        return True
    return False


def _graph_context_is_rich(graph_context: str) -> bool:
    t = graph_context or ""
    if "한약재:" in t and "정보가 없습니다" not in t:
        return True
    if "효능=" in t and "등록된 한약재:" not in t:
        return True
    return False


_JSON_ARRAY = re.compile(r"\[[\s\S]*\]")


def _sql_context_has_useful_rows(sql_redis_context: str) -> bool:
    s = (sql_redis_context or "").strip()
    if not s:
        return False
    if "조회 중 오류" in s or "시간이 초과" in s:
        return False
    if "재고/단가 조회는 SELECT" in s:
        return False
    m = _JSON_ARRAY.search(s)
    if m:
        try:
            data = json.loads(m.group())
            if isinstance(data, list) and len(data) > 0:
                return True
        except json.JSONDecodeError:
            pass
    if "캐시 데이터" in s and len(s) > 120:
        return True
    if "--- DB 조회 결과 ---" in s and len(s) > 200 and "[]" not in s:
        return True
    return False


def classify_stage3_coverage(
    graph_context: str,
    sql_redis_context: str,
) -> CoverageNotice:
    g_miss = _graph_context_is_missing(graph_context)
    g_rich = _graph_context_is_rich(graph_context)
    sql_ok = _sql_context_has_useful_rows(sql_redis_context)

    if g_rich and not sql_ok:
        return CoverageNotice(CoverageCase.GRAPH_ONLY_NO_DB, (WARN_GRAPH_ONLY_NO_DB,))
    if g_miss and sql_ok:
        return CoverageNotice(CoverageCase.DB_ONLY_NO_GRAPH, (WARN_DB_ONLY_NO_GRAPH,))
    if g_miss and not sql_ok:
        return CoverageNotice(CoverageCase.NEITHER, ())
    return CoverageNotice(CoverageCase.BOTH, ())


def format_coverage_prefix(notice: CoverageNotice) -> str:
    if not notice.lines:
        return ""
    return "\n".join(notice.lines) + "\n\n"


def build_coverage_block_stage3(graph_context: str, sql_redis_context: str) -> str:
    n = classify_stage3_coverage(graph_context, sql_redis_context)
    return format_coverage_prefix(n)


def build_coverage_block_stage2_graph_only() -> str:
    return WARN_STAGE2_GRAPH_PATH + "\n\n"


def extract_herb_ids_from_text(text: str) -> list[str]:
    """Find H_XXX tokens in arbitrary graph/SQL blobs."""
    return sorted(set(re.findall(r"\bH_[A-Z0-9_]+\b", text or "")))
