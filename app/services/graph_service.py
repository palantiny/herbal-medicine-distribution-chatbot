"""
한약재 지식 그래프 서비스 (Neo4j)
Stage1 RouterOutput의 target_intents에 대응하는 고정 Cypher 템플릿 실행.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from neo4j import AsyncGraphDatabase

from app.core.config import get_settings
from app.schemas.stage1_router import ExtractedNode, GraphIntent, RouterOutput

logger = logging.getLogger(__name__)
settings = get_settings()

_driver = None

# intent 병합 시 고정 순서 (디버깅·재현성)
_INTENT_ORDER: list[GraphIntent] = [
    "SEARCH_TEMP",
    "SEARCH_TASTE",
    "SEARCH_MERIDIAN",
    "SEARCH_EFFICACY",
    "SEARCH_SYMPTOM",
    "SEARCH_FORMULA_CONTAINS",
    "SEARCH_CONTRAINDICATION",
    "SEARCH_DOSAGE_FORM",
    "SEARCH_DISTRIBUTION_ALL",
    "SEARCH_HERB_BY_MAKER",
    "SEARCH_HERB_BY_ORIGIN",
    "SEARCH_PRICE_INFO",
]
_INTENT_RANK: dict[GraphIntent, int] = {k: i for i, k in enumerate(_INTENT_ORDER)}


async def get_neo4j_driver():
    """Neo4j 비동기 드라이버 반환 (지연 초기화)."""
    global _driver
    if _driver is None and settings.NEO4J_URI:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j():
    """Neo4j 드라이버 종료."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


def _first_name(nodes: list[ExtractedNode], *types: str) -> str | None:
    for t in types:
        for n in nodes:
            if n.node_type == t and n.node_name.strip():
                return n.node_name.strip()
    return None


def _all_herb_names(nodes: list[ExtractedNode]) -> list[str]:
    return [n.node_name.strip() for n in nodes if n.node_type == "Herb" and n.node_name.strip()]


def _format_herb_list(header: str, label: str, herb_rows: list[Any] | None) -> str:
    """
    1-hop 역방향 브랜치 공통 포맷터.
    herb_rows: [{name: "감초", pids: ["P001", "P002"]}, ...]
    → 각 약재마다 '[연결된 product_id: ...]' 태그를 붙여 bullet 리스트로 출력.
    """
    rows = [x for x in (herb_rows or []) if x and x.get("name")]
    if not rows:
        return f"{header}\n{label}: 없음"
    # 이름순 정렬 (동일 속성 쿼리에서 결정적 순서 보장)
    rows = sorted(rows, key=lambda r: r["name"])
    lines = [header, f"{label}:"]
    for r in rows:
        valid_pids = [pid for pid in (r.get("pids") or []) if pid]
        tag = f" [연결된 product_id: {', '.join(valid_pids)}]" if valid_pids else ""
        lines.append(f"  - {r['name']}{tag}")
    return "\n".join(lines)


# ── 템플릿별 실행 (세션은 호출자가 열지 않음 — 코루틴마다 독립 session) ──


async def _tpl_search_temp(driver: Any, nodes: list[ExtractedNode]) -> str:
    herb = _first_name(nodes, "Herb")
    nt = _first_name(nodes, "NatureTemp")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_TEMP]->(t:NatureTemp)
                WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                RETURN h.name AS herb,
                       collect(DISTINCT t.name) AS temps,
                       collect(DISTINCT p.product_id) AS product_ids
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 성질(NatureTemp) 정보가 없습니다."
            temps = [x for x in (rec["temps"] or []) if x]
            pids = [x for x in (rec["product_ids"] or []) if x]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            return f"약재: {rec['herb']}{pid_tag}\n성질: {', '.join(temps) if temps else '없음'}"
        if nt:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_TEMP]->(t:NatureTemp)
                WHERE t.name = $tname
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                WITH t, h, collect(DISTINCT p.product_id) AS pids
                RETURN t.name AS temp,
                       collect({name: h.name, pids: pids}) AS herbs
                """,
                tname=nt,
            )
            rec = await result.single()
            if not rec or not rec["temp"]:
                return f"성질 '{nt}'에 해당하는 약재를 찾지 못했습니다."
            return _format_herb_list(f"성질: {rec['temp']}", "해당 약재", rec["herbs"])
        return "SEARCH_TEMP: Herb 또는 NatureTemp 노드가 필요합니다."


async def _tpl_search_taste(driver: Any, nodes: list[ExtractedNode]) -> str:
    herb = _first_name(nodes, "Herb")
    taste = _first_name(nodes, "NatureTaste")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_TASTE]->(t:NatureTaste)
                WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                RETURN h.name AS herb,
                       collect(DISTINCT t.name) AS tastes,
                       collect(DISTINCT p.product_id) AS product_ids
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 맛(NatureTaste) 정보가 없습니다."
            tastes = [x for x in (rec["tastes"] or []) if x]
            pids = [x for x in (rec["product_ids"] or []) if x]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            return f"약재: {rec['herb']}{pid_tag}\n맛: {', '.join(tastes) if tastes else '없음'}"
        if taste:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_TASTE]->(t:NatureTaste)
                WHERE t.name = $tname
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                WITH t, h, collect(DISTINCT p.product_id) AS pids
                RETURN t.name AS taste,
                       collect({name: h.name, pids: pids}) AS herbs
                """,
                tname=taste,
            )
            rec = await result.single()
            if not rec or not rec["taste"]:
                return f"맛 '{taste}'에 해당하는 약재를 찾지 못했습니다."
            return _format_herb_list(f"맛: {rec['taste']}", "해당 약재", rec["herbs"])
        return "SEARCH_TASTE: Herb 또는 NatureTaste 노드가 필요합니다."


async def _tpl_search_meridian(driver: Any, nodes: list[ExtractedNode]) -> str:
    herb = _first_name(nodes, "Herb")
    mer = _first_name(nodes, "Meridian")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb:
            result = await session.run(
                """
                MATCH (h:Herb)-[:ACTS_ON]->(m:Meridian)
                WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                RETURN h.name AS herb,
                       collect(DISTINCT m.name) AS meridians,
                       collect(DISTINCT p.product_id) AS product_ids
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 귀경(Meridian) 정보가 없습니다."
            ms = [x for x in (rec["meridians"] or []) if x]
            pids = [x for x in (rec["product_ids"] or []) if x]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            return f"약재: {rec['herb']}{pid_tag}\n귀경: {', '.join(ms) if ms else '없음'}"
        if mer:
            result = await session.run(
                """
                MATCH (h:Herb)-[:ACTS_ON]->(m:Meridian)
                WHERE m.name = $mname
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                WITH m, h, collect(DISTINCT p.product_id) AS pids
                RETURN m.name AS meridian,
                       collect({name: h.name, pids: pids}) AS herbs
                """,
                mname=mer,
            )
            rec = await result.single()
            if not rec or not rec["meridian"]:
                return f"귀경 '{mer}'에 작용하는 약재를 찾지 못했습니다."
            return _format_herb_list(f"귀경: {rec['meridian']}", "해당 약재", rec["herbs"])
        return "SEARCH_MERIDIAN: Herb 또는 Meridian 노드가 필요합니다."


async def _tpl_search_efficacy(driver: Any, nodes: list[ExtractedNode]) -> str:
    herb = _first_name(nodes, "Herb")
    eff = _first_name(nodes, "Efficacy")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_EFFICACY]->(e:Efficacy)
                WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                RETURN h.name AS herb,
                       collect(DISTINCT e.name) AS efficacies,
                       collect(DISTINCT p.product_id) AS product_ids
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 효능 정보가 없습니다."
            es = [x for x in (rec["efficacies"] or []) if x]
            pids = [x for x in (rec["product_ids"] or []) if x]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            return f"약재: {rec['herb']}{pid_tag}\n효능: {', '.join(es) if es else '없음'}"
        if eff:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_EFFICACY]->(e:Efficacy)
                WHERE e.name = $ename
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                WITH e, h, collect(DISTINCT p.product_id) AS pids
                RETURN e.name AS efficacy,
                       collect({name: h.name, pids: pids}) AS herbs
                """,
                ename=eff,
            )
            rec = await result.single()
            if not rec or not rec["efficacy"]:
                return f"효능 '{eff}'에 해당하는 약재를 찾지 못했습니다."
            return _format_herb_list(f"효능: {rec['efficacy']}", "해당 약재", rec["herbs"])
        return "SEARCH_EFFICACY: Herb 또는 Efficacy 노드가 필요합니다."


async def _tpl_search_symptom(driver: Any, nodes: list[ExtractedNode]) -> str:
    herb = _first_name(nodes, "Herb")
    sym = _first_name(nodes, "Symptom")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb:
            result = await session.run(
                """
                MATCH (h:Herb)-[:TREATS]->(s:Symptom)
                WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                RETURN h.name AS herb,
                       collect(DISTINCT s.name) AS symptoms,
                       collect(DISTINCT p.product_id) AS product_ids
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 치료 증상 정보가 없습니다."
            ss = [x for x in (rec["symptoms"] or []) if x]
            pids = [x for x in (rec["product_ids"] or []) if x]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            return f"약재: {rec['herb']}{pid_tag}\n치료/관련 증상: {', '.join(ss) if ss else '없음'}"
        if sym:
            result = await session.run(
                """
                MATCH (h:Herb)-[:TREATS]->(s:Symptom)
                WHERE s.name = $sname
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                WITH s, h, collect(DISTINCT p.product_id) AS pids
                RETURN s.name AS symptom,
                       collect({name: h.name, pids: pids}) AS herbs
                """,
                sname=sym,
            )
            rec = await result.single()
            if not rec or not rec["symptom"]:
                return f"증상 '{sym}'에 쓰이는 약재를 찾지 못했습니다."
            return _format_herb_list(f"증상: {rec['symptom']}", "해당 약재", rec["herbs"])
        return "SEARCH_SYMPTOM: Herb 또는 Symptom 노드가 필요합니다."


async def _tpl_search_formula_contains(driver: Any, nodes: list[ExtractedNode]) -> str:
    formula = _first_name(nodes, "Formula")
    herb = _first_name(nodes, "Herb")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if formula:
            result = await session.run(
                """
                MATCH (f:Formula)-[:CONTAINS]->(h:Herb)
                WHERE f.name = $fname
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                WITH f, h, collect(DISTINCT p.product_id) AS pids
                RETURN f.name AS formula,
                       collect({name: h.name, pids: pids}) AS herbs
                """,
                fname=formula,
            )
            rec = await result.single()
            if not rec or not rec["formula"]:
                return f"처방 '{formula}'를 찾지 못했습니다."
            herb_rows = [x for x in (rec["herbs"] or []) if x and x.get("name")]
            if not herb_rows:
                return f"처방: {rec['formula']}\n포함 약재: 없음"
            herb_lines = []
            for hr in herb_rows:
                valid_pids = [pid for pid in (hr.get("pids") or []) if pid]
                tag = f" [연결된 product_id: {', '.join(valid_pids)}]" if valid_pids else ""
                herb_lines.append(f"{hr['name']}{tag}")
            return f"처방: {rec['formula']}\n포함 약재:\n  - " + "\n  - ".join(herb_lines)
        if herb:
            result = await session.run(
                """
                MATCH (f:Formula)-[:CONTAINS]->(h:Herb)
                WHERE h.name = $hname OR $hname IN coalesce(h.synonyms, [])
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                RETURN h.name AS herb,
                       collect(DISTINCT f.name) AS formulas,
                       collect(DISTINCT p.product_id) AS product_ids
                """,
                hname=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'가 포함된 처방을 찾지 못했습니다."
            fs = [x for x in (rec["formulas"] or []) if x]
            pids = [x for x in (rec["product_ids"] or []) if x]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            return f"약재: {rec['herb']}{pid_tag}\n포함된 처방: {', '.join(fs) if fs else '없음'}"
        return "SEARCH_FORMULA_CONTAINS: Formula 또는 Herb 노드가 필요합니다."


async def _tpl_search_contraindication(driver: Any, nodes: list[ExtractedNode]) -> str:
    herbs = _all_herb_names(nodes)
    if not herbs:
        return "SEARCH_CONTRAINDICATION: Herb 노드가 필요합니다."
    hname = herbs[0]
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(
            """
            MATCH (h:Herb)
            WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
            OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(ph:Product)
            WITH h, collect(DISTINCT ph.product_id) AS h_pids
            OPTIONAL MATCH (h)-[:CONTRAINDICATES]->(c:Herb)
            OPTIONAL MATCH (c)-[:HAS_PRODUCT]->(pc:Product)
            WITH h, h_pids, c, collect(DISTINCT pc.product_id) AS c_pids
            WITH h, h_pids,
                 collect(CASE WHEN c IS NULL THEN NULL
                              ELSE {name: c.name, pids: c_pids} END) AS contras
            RETURN h.name AS herb, h_pids AS product_ids, contras
            """,
            name=hname,
        )
        rec = await result.single()
        if not rec or not rec["herb"]:
            return f"약재 '{hname}'에 대한 상극/금기 정보가 없습니다."
        pids = [x for x in (rec["product_ids"] or []) if x]
        pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
        header = f"약재: {rec['herb']}{pid_tag}"
        return _format_herb_list(header, "상극/금기 약재", rec["contras"])


async def _tpl_search_dosage_form(driver: Any, nodes: list[ExtractedNode]) -> str:
    """
    1-hop 지식 템플릿: (Herb)-[:CAN_PREPARED_AS]->(DosageForm)
    - 약재 기준: 해당 약재가 어떤 제형으로 조제 가능한지 조회
    - 제형 기준: 해당 제형으로 조제 가능한 약재 목록 조회
    양쪽 브랜치 모두 약재별 product_id를 태그로 반환.
    """
    herb = _first_name(nodes, "Herb")
    form = _first_name(nodes, "DosageForm")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb:
            result = await session.run(
                """
                MATCH (h:Herb)-[:CAN_PREPARED_AS]->(df:DosageForm)
                WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                RETURN h.name AS herb,
                       collect(DISTINCT df.name) AS forms,
                       collect(DISTINCT p.product_id) AS product_ids
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 제형(DosageForm) 정보가 없습니다."
            forms = [x for x in (rec["forms"] or []) if x]
            pids = [x for x in (rec["product_ids"] or []) if x]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            return f"약재: {rec['herb']}{pid_tag}\n조제 가능 제형: {', '.join(forms) if forms else '없음'}"
        if form:
            result = await session.run(
                """
                MATCH (h:Herb)-[:CAN_PREPARED_AS]->(df:DosageForm)
                WHERE df.name = $fname
                OPTIONAL MATCH (h)-[:HAS_PRODUCT]->(p:Product)
                WITH df, h, collect(DISTINCT p.product_id) AS pids
                RETURN df.name AS form,
                       collect({name: h.name, pids: pids}) AS herbs
                """,
                fname=form,
            )
            rec = await result.single()
            if not rec or not rec["form"]:
                return f"제형 '{form}'에 해당하는 약재를 찾지 못했습니다."
            return _format_herb_list(f"제형: {rec['form']}", "조제 가능 약재", rec["herbs"])
        return "SEARCH_DOSAGE_FORM: Herb 또는 DosageForm 노드가 필요합니다."


async def _tpl_search_distribution_all(driver: Any, nodes: list[ExtractedNode]) -> str:
    herb = _first_name(nodes, "Herb")
    if not herb:
        return "SEARCH_DISTRIBUTION_ALL: Herb 노드가 필요합니다."
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(
            """
            MATCH (h:Herb)-[:HAS_PRODUCT]->(p:Product)
            WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
            OPTIONAL MATCH (p)-[:MANUFACTURED_BY]->(mk:Maker)
            OPTIONAL MATCH (p)-[:ORIGINATES_FROM]->(o:Origin)
            RETURN h.name AS herb, p.product_id AS product_id, p.type AS type,
                   p.pack_unit AS pack_unit, p.pack_price AS pack_price, p.box_qty AS box_qty,
                   mk.name AS maker, o.name AS origin
            ORDER BY p.product_id
            """,
            name=herb,
        )
        rows = [r async for r in result]
        if not rows:
            return f"약재 '{herb}'에 연결된 Product가 없습니다."
        all_pids = sorted({r["product_id"] for r in rows if r["product_id"]})
        pid_tag = f" [연결된 product_id: {', '.join(all_pids)}]" if all_pids else ""
        herb_name = rows[0]["herb"] or herb
        lines = [f"[유통 요약] 약재: {herb_name}{pid_tag}"]
        for r in rows:
            parts = [f"  [product_id={r['product_id']}]", f"유형={r['type']}"]
            if r["maker"]:
                parts.append(f"제조사={r['maker']}")
            if r["origin"]:
                parts.append(f"원산지={r['origin']}")
            if r["pack_unit"]:
                parts.append(f"포장단위={r['pack_unit']}")
            if r["box_qty"]:
                parts.append(f"박스수량={r['box_qty']}")
            if r["pack_price"]:
                parts.append(f"포장단가={r['pack_price']}원")
            lines.append(", ".join(parts))
        pr_result = await session.run(
            """
            MATCH (h:Herb)-[:HAS_PRODUCT]->(p:Product)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
            WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
            WITH p, pr ORDER BY pr.month DESC
            WITH p, collect(pr)[0] AS latest
            OPTIONAL MATCH (p)-[:MANUFACTURED_BY]->(mk:Maker)
            RETURN p.product_id AS product_id, latest.month AS month,
                   latest.price_per_geun AS price_per_geun, latest.status AS status, mk.name AS maker
            ORDER BY p.product_id
            """,
            name=herb,
        )
        lines.append("[최신 가격 요약]")
        any_p = False
        async for r in pr_result:
            any_p = True
            extra = f", 제조사={r['maker']}" if r["maker"] else ""
            month_tag = f" ({r['month']})" if r["month"] else ""
            if r["price_per_geun"] is None:
                lines.append(
                    f"  [product_id={r['product_id']}]: 근당가격=가격정보없음{month_tag}{extra}"
                )
            else:
                lines.append(
                    f"  [product_id={r['product_id']}]: 근당 {r['price_per_geun']}원{month_tag}{extra}"
                )
        if not any_p:
            lines.append("  (가격 이력 없음)")
        return "\n".join(lines)


async def _tpl_search_herb_by_maker(driver: Any, nodes: list[ExtractedNode]) -> str:
    """
    2-hop 확장 템플릿: Maker → Product → {Origin, PriceRecord} → Herb
    사용자가 제조사로 질문하면 상품·원산지·최신 가격·약재명을 한 번에 반환.
    """
    maker = _first_name(nodes, "Maker")
    if not maker:
        return "SEARCH_HERB_BY_MAKER: Maker 노드가 필요합니다."
    herb_filter = _first_name(nodes, "Herb")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb_filter:
            result = await session.run(
                """
                MATCH (mk:Maker)<-[:MANUFACTURED_BY]-(p:Product)<-[:HAS_PRODUCT]-(h:Herb)
                WHERE mk.name = $mname AND (h.name = $hname OR $hname IN coalesce(h.synonyms, []))
                OPTIONAL MATCH (p)-[:ORIGINATES_FROM]->(o:Origin)
                OPTIONAL MATCH (p)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
                WITH h, p, o, pr ORDER BY pr.month DESC
                WITH h, p, o, collect(pr)[0] AS latest
                RETURN h.name AS herb,
                       p.product_id AS product_id,
                       p.type AS type,
                       p.pack_unit AS pack_unit,
                       p.box_qty AS box_qty,
                       p.pack_price AS pack_price,
                       o.name AS origin,
                       latest.month AS price_month,
                       latest.price_per_geun AS price_per_geun,
                       latest.status AS price_status
                ORDER BY h.name, product_id
                """,
                mname=maker,
                hname=herb_filter,
            )
        else:
            result = await session.run(
                """
                MATCH (mk:Maker)<-[:MANUFACTURED_BY]-(p:Product)<-[:HAS_PRODUCT]-(h:Herb)
                WHERE mk.name = $mname
                OPTIONAL MATCH (p)-[:ORIGINATES_FROM]->(o:Origin)
                OPTIONAL MATCH (p)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
                WITH h, p, o, pr ORDER BY pr.month DESC
                WITH h, p, o, collect(pr)[0] AS latest
                RETURN h.name AS herb,
                       p.product_id AS product_id,
                       p.type AS type,
                       p.pack_unit AS pack_unit,
                       p.box_qty AS box_qty,
                       p.pack_price AS pack_price,
                       o.name AS origin,
                       latest.month AS price_month,
                       latest.price_per_geun AS price_per_geun,
                       latest.status AS price_status
                ORDER BY h.name, product_id
                LIMIT 80
                """,
                mname=maker,
            )
        rows = [r async for r in result]
        if not rows:
            return f"제조사 '{maker}'에 해당하는 약재/상품을 찾지 못했습니다."
        by_herb: dict[str, list[Any]] = {}
        for r in rows:
            if r["herb"]:
                by_herb.setdefault(r["herb"], []).append(r)
        lines = [f"제조사: {maker}", "[연결된 약재 및 상품]"]
        for herb_name in sorted(by_herb.keys()):
            items = by_herb[herb_name]
            pids = [r["product_id"] for r in items if r["product_id"]]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            lines.append(f"- {herb_name}{pid_tag}")
            for r in items:
                if not r["product_id"]:
                    continue
                parts = [f"  · [product_id={r['product_id']}]"]
                if r["type"]:
                    parts.append(f"유형={r['type']}")
                if r["origin"]:
                    parts.append(f"원산지={r['origin']}")
                if r["pack_unit"]:
                    parts.append(f"포장단위={r['pack_unit']}")
                if r["box_qty"]:
                    parts.append(f"박스수량={r['box_qty']}")
                if r["pack_price"]:
                    parts.append(f"포장단가={r['pack_price']}원")
                month = r["price_month"] or "-"
                status = r["price_status"] or ""
                status_tag = f"({status})" if status else ""
                if r["price_per_geun"] is None:
                    parts.append(f"근당가격=가격정보없음@{month}{status_tag}")
                else:
                    parts.append(f"근당가격={r['price_per_geun']}원@{month}{status_tag}")
                lines.append(", ".join(parts))
        return "\n".join(lines)


async def _tpl_search_herb_by_origin(driver: Any, nodes: list[ExtractedNode]) -> str:
    """
    2-hop 확장 템플릿: Origin → Product → {Maker, PriceRecord} → Herb
    사용자가 원산지로 질문하면 상품·제조사·최신 가격·약재명을 한 번에 반환.
    """
    origin = _first_name(nodes, "Origin")
    if not origin:
        return "SEARCH_HERB_BY_ORIGIN: Origin 노드가 필요합니다."
    herb_filter = _first_name(nodes, "Herb")
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        if herb_filter:
            result = await session.run(
                """
                MATCH (o:Origin)<-[:ORIGINATES_FROM]-(p:Product)<-[:HAS_PRODUCT]-(h:Herb)
                WHERE o.name = $oname AND (h.name = $hname OR $hname IN coalesce(h.synonyms, []))
                OPTIONAL MATCH (p)-[:MANUFACTURED_BY]->(mk:Maker)
                OPTIONAL MATCH (p)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
                WITH h, p, mk, pr ORDER BY pr.month DESC
                WITH h, p, mk, collect(pr)[0] AS latest
                RETURN h.name AS herb,
                       p.product_id AS product_id,
                       p.type AS type,
                       p.pack_unit AS pack_unit,
                       p.box_qty AS box_qty,
                       p.pack_price AS pack_price,
                       mk.name AS maker,
                       latest.month AS price_month,
                       latest.price_per_geun AS price_per_geun,
                       latest.status AS price_status
                ORDER BY h.name, product_id
                """,
                oname=origin,
                hname=herb_filter,
            )
        else:
            result = await session.run(
                """
                MATCH (o:Origin)<-[:ORIGINATES_FROM]-(p:Product)<-[:HAS_PRODUCT]-(h:Herb)
                WHERE o.name = $oname
                OPTIONAL MATCH (p)-[:MANUFACTURED_BY]->(mk:Maker)
                OPTIONAL MATCH (p)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
                WITH h, p, mk, pr ORDER BY pr.month DESC
                WITH h, p, mk, collect(pr)[0] AS latest
                RETURN h.name AS herb,
                       p.product_id AS product_id,
                       p.type AS type,
                       p.pack_unit AS pack_unit,
                       p.box_qty AS box_qty,
                       p.pack_price AS pack_price,
                       mk.name AS maker,
                       latest.month AS price_month,
                       latest.price_per_geun AS price_per_geun,
                       latest.status AS price_status
                ORDER BY h.name, product_id
                LIMIT 80
                """,
                oname=origin,
            )
        rows = [r async for r in result]
        if not rows:
            return f"원산지 '{origin}'에 해당하는 약재/상품을 찾지 못했습니다."
        by_herb: dict[str, list[Any]] = {}
        for r in rows:
            if r["herb"]:
                by_herb.setdefault(r["herb"], []).append(r)
        lines = [f"원산지: {origin}", "[연결된 약재 및 상품]"]
        for herb_name in sorted(by_herb.keys()):
            items = by_herb[herb_name]
            pids = [r["product_id"] for r in items if r["product_id"]]
            pid_tag = f" [연결된 product_id: {', '.join(pids)}]" if pids else ""
            lines.append(f"- {herb_name}{pid_tag}")
            for r in items:
                if not r["product_id"]:
                    continue
                parts = [f"  · [product_id={r['product_id']}]"]
                if r["type"]:
                    parts.append(f"유형={r['type']}")
                if r["maker"]:
                    parts.append(f"제조사={r['maker']}")
                if r["pack_unit"]:
                    parts.append(f"포장단위={r['pack_unit']}")
                if r["box_qty"]:
                    parts.append(f"박스수량={r['box_qty']}")
                if r["pack_price"]:
                    parts.append(f"포장단가={r['pack_price']}원")
                month = r["price_month"] or "-"
                status = r["price_status"] or ""
                status_tag = f"({status})" if status else ""
                if r["price_per_geun"] is None:
                    parts.append(f"근당가격=가격정보없음@{month}{status_tag}")
                else:
                    parts.append(f"근당가격={r['price_per_geun']}원@{month}{status_tag}")
                lines.append(", ".join(parts))
        return "\n".join(lines)


async def _tpl_search_price_info(driver: Any, nodes: list[ExtractedNode]) -> str:
    """
    2-hop 확장 템플릿: Herb → Product → PriceRecord → {Maker, Origin}
    가격 질문에는 상품 상세(포장단위/박스수량/유형)와 제조사·원산지까지 함께 반환.
    """
    herb = _first_name(nodes, "Herb")
    if not herb:
        return "SEARCH_PRICE_INFO: Herb 노드가 필요합니다."
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(
            """
            MATCH (h:Herb)-[:HAS_PRODUCT]->(p:Product)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
            WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
            OPTIONAL MATCH (p)-[:MANUFACTURED_BY]->(mk:Maker)
            OPTIONAL MATCH (p)-[:ORIGINATES_FROM]->(o:Origin)
            RETURN h.name AS herb,
                   p.product_id AS product_id,
                   p.type AS type,
                   p.pack_unit AS pack_unit,
                   p.box_qty AS box_qty,
                   p.pack_price AS pack_price,
                   pr.month AS month,
                   pr.price_per_geun AS price_per_geun,
                   pr.status AS status,
                   mk.name AS maker,
                   o.name AS origin
            ORDER BY p.product_id, pr.month DESC
            LIMIT 120
            """,
            name=herb,
        )
        rows = [r async for r in result]
        if not rows:
            return f"약재 '{herb}'의 가격 이력(PriceRecord)이 없습니다."
        # 전체 product_id 목록을 약재명 링크용으로 집계
        all_pids = sorted({r["product_id"] for r in rows if r["product_id"]})
        pid_tag = f" [연결된 product_id: {', '.join(all_pids)}]" if all_pids else ""
        herb_name = rows[0]["herb"] or herb
        lines = [f"약재: {herb_name}{pid_tag}", "[가격 이력]"]
        for r in rows:
            parts = [f"  [product_id={r['product_id']}]"]
            if r["type"]:
                parts.append(f"유형={r['type']}")
            if r["price_per_geun"] is None:
                parts.append(f"{r['month']} 근당가격=가격정보없음")
            else:
                parts.append(f"{r['month']} 근당 {r['price_per_geun']}원")
            if r["status"]:
                parts.append(f"상태={r['status']}")
            if r["maker"]:
                parts.append(f"제조사={r['maker']}")
            if r["origin"]:
                parts.append(f"원산지={r['origin']}")
            if r["pack_unit"]:
                parts.append(f"포장단위={r['pack_unit']}")
            if r["box_qty"]:
                parts.append(f"박스수량={r['box_qty']}")
            if r["pack_price"]:
                parts.append(f"포장단가={r['pack_price']}원")
            lines.append(", ".join(parts))
        return "\n".join(lines) if len(lines) > 2 else f"약재: {herb_name}{pid_tag}\n(가격 이력 없음)"


async def _dispatch_intent(intent: GraphIntent, nodes: list[ExtractedNode]) -> str:
    driver = await get_neo4j_driver()
    if not driver:
        return "Neo4j가 설정되지 않았습니다."
    try:
        if intent == "SEARCH_TEMP":
            return await _tpl_search_temp(driver, nodes)
        if intent == "SEARCH_TASTE":
            return await _tpl_search_taste(driver, nodes)
        if intent == "SEARCH_MERIDIAN":
            return await _tpl_search_meridian(driver, nodes)
        if intent == "SEARCH_EFFICACY":
            return await _tpl_search_efficacy(driver, nodes)
        if intent == "SEARCH_SYMPTOM":
            return await _tpl_search_symptom(driver, nodes)
        if intent == "SEARCH_FORMULA_CONTAINS":
            return await _tpl_search_formula_contains(driver, nodes)
        if intent == "SEARCH_CONTRAINDICATION":
            return await _tpl_search_contraindication(driver, nodes)
        if intent == "SEARCH_DOSAGE_FORM":
            return await _tpl_search_dosage_form(driver, nodes)
        if intent == "SEARCH_DISTRIBUTION_ALL":
            return await _tpl_search_distribution_all(driver, nodes)
        if intent == "SEARCH_HERB_BY_MAKER":
            return await _tpl_search_herb_by_maker(driver, nodes)
        if intent == "SEARCH_HERB_BY_ORIGIN":
            return await _tpl_search_herb_by_origin(driver, nodes)
        if intent == "SEARCH_PRICE_INFO":
            return await _tpl_search_price_info(driver, nodes)
        return f"알 수 없는 intent: {intent}"
    except Exception as e:
        logger.exception("Neo4j 템플릿 실패 intent=%s: %s", intent, e)
        return f"조회 오류: {e}"


async def execute_router_graph_search(router: RouterOutput) -> str:
    """
    route가 SEARCH_GRAPH일 때 target_intents를 병렬 실행하고, 완료 후 하나의 문자열로 합친다.
    intent마다 독립 Neo4j session; 동시 실행 수는 NEO4J_QUERY_PARALLEL_MAX로 제한.
    """
    if router.route != "SEARCH_GRAPH":
        return ""
    if not router.target_intents:
        return (
            "[SEARCH_GRAPH] target_intents가 비어 있습니다. "
            "탐색할 템플릿을 지정해 주세요.\n"
        )

    seen: set[GraphIntent] = set()
    ordered: list[GraphIntent] = []
    for i in router.target_intents:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    ordered.sort(key=lambda x: _INTENT_RANK.get(x, 99))

    sem = asyncio.Semaphore(max(1, settings.NEO4J_QUERY_PARALLEL_MAX))
    nodes = list(router.extracted_nodes)

    async def _run(intent: GraphIntent) -> tuple[GraphIntent, str]:
        async with sem:
            text = await _dispatch_intent(intent, nodes)
            return intent, text

    pairs = await asyncio.gather(*[_run(i) for i in ordered], return_exceptions=True)
    parts: list[str] = []
    for item in pairs:
        if isinstance(item, BaseException):
            logger.exception("병렬 그래프 조회 실패: %s", item)
            parts.append(f"[오류] {item!s}")
            continue
        intent, text = item
        parts.append(f"[{intent}]\n{text}")

    return "\n\n".join(parts) + "\n"
