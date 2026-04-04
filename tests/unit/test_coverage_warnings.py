"""Palantiny coverage notices for Stage 3 / graph vs SQL heuristics."""

from palantiny.contracts.coverage import CoverageCase
from palantiny.orchestration.coverage import (
    build_coverage_block_stage2_graph_only,
    build_coverage_block_stage3,
    classify_stage3_coverage,
    extract_herb_ids_from_text,
)


def test_stage3_graph_rich_sql_empty_triggers_b():
    gc = "한약재: 인삼\n효능: 대보원기"
    sql = "--- DB 조회 결과 ---\n[]"
    n = classify_stage3_coverage(gc, sql)
    assert n.case == CoverageCase.GRAPH_ONLY_NO_DB
    block = build_coverage_block_stage3(gc, sql)
    assert "[시스템 안내]" in block
    assert "PostgreSQL" in block


def test_stage3_graph_miss_sql_rows_triggers_c():
    gc = "'감초'에 대한 지식 그래프 정보가 없습니다."
    sql = '--- DB 조회 결과 ---\n[{"herb_name": "감초", "stock_quantity": 10}]'
    n = classify_stage3_coverage(gc, sql)
    assert n.case == CoverageCase.DB_ONLY_NO_GRAPH
    block = build_coverage_block_stage3(gc, sql)
    assert "지식 그래프" in block


def test_stage3_both_ok_no_prefix():
    gc = "한약재: 감초\n효능: 보익기"
    sql = '[{"herb_name": "감초", "price": 100}]'
    n = classify_stage3_coverage(gc, sql)
    assert n.case == CoverageCase.BOTH
    assert build_coverage_block_stage3(gc, sql) == ""


def test_stage2_graph_only_prefix():
    s = build_coverage_block_stage2_graph_only()
    assert "지식 그래프만" in s


def test_extract_herb_ids():
    assert extract_herb_ids_from_text("stub H_CSV_A1B2C3D4 and H_010") == ["H_010", "H_CSV_A1B2C3D4"]
