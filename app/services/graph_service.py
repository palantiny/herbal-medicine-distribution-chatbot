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
                RETURN h.name AS herb, collect(DISTINCT t.name) AS temps
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 성질(NatureTemp) 정보가 없습니다."
            temps = [x for x in (rec["temps"] or []) if x]
            return f"약재: {rec['herb']}\n성질: {', '.join(temps) if temps else '없음'}"
        if nt:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_TEMP]->(t:NatureTemp)
                WHERE t.name = $tname
                RETURN collect(DISTINCT h.name) AS herbs, t.name AS temp
                """,
                tname=nt,
            )
            rec = await result.single()
            if not rec or not rec["temp"]:
                return f"성질 '{nt}'에 해당하는 약재를 찾지 못했습니다."
            herbs = [x for x in (rec["herbs"] or []) if x]
            return f"성질: {rec['temp']}\n해당 약재: {', '.join(herbs) if herbs else '없음'}"
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
                RETURN h.name AS herb, collect(DISTINCT t.name) AS tastes
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 맛(NatureTaste) 정보가 없습니다."
            tastes = [x for x in (rec["tastes"] or []) if x]
            return f"약재: {rec['herb']}\n맛: {', '.join(tastes) if tastes else '없음'}"
        if taste:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_TASTE]->(t:NatureTaste)
                WHERE t.name = $tname
                RETURN collect(DISTINCT h.name) AS herbs, t.name AS taste
                """,
                tname=taste,
            )
            rec = await result.single()
            if not rec or not rec["taste"]:
                return f"맛 '{taste}'에 해당하는 약재를 찾지 못했습니다."
            herbs = [x for x in (rec["herbs"] or []) if x]
            return f"맛: {rec['taste']}\n해당 약재: {', '.join(herbs) if herbs else '없음'}"
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
                RETURN h.name AS herb, collect(DISTINCT m.name) AS meridians
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 귀경(Meridian) 정보가 없습니다."
            ms = [x for x in (rec["meridians"] or []) if x]
            return f"약재: {rec['herb']}\n귀경: {', '.join(ms) if ms else '없음'}"
        if mer:
            result = await session.run(
                """
                MATCH (h:Herb)-[:ACTS_ON]->(m:Meridian)
                WHERE m.name = $mname
                RETURN collect(DISTINCT h.name) AS herbs, m.name AS meridian
                """,
                mname=mer,
            )
            rec = await result.single()
            if not rec or not rec["meridian"]:
                return f"귀경 '{mer}'에 작용하는 약재를 찾지 못했습니다."
            herbs = [x for x in (rec["herbs"] or []) if x]
            return f"귀경: {rec['meridian']}\n해당 약재: {', '.join(herbs) if herbs else '없음'}"
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
                RETURN h.name AS herb, collect(DISTINCT e.name) AS efficacies
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 효능 정보가 없습니다."
            es = [x for x in (rec["efficacies"] or []) if x]
            return f"약재: {rec['herb']}\n효능: {', '.join(es) if es else '없음'}"
        if eff:
            result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_EFFICACY]->(e:Efficacy)
                WHERE e.name = $ename
                RETURN collect(DISTINCT h.name) AS herbs, e.name AS efficacy
                """,
                ename=eff,
            )
            rec = await result.single()
            if not rec or not rec["efficacy"]:
                return f"효능 '{eff}'에 해당하는 약재를 찾지 못했습니다."
            herbs = [x for x in (rec["herbs"] or []) if x]
            return f"효능: {rec['efficacy']}\n해당 약재: {', '.join(herbs) if herbs else '없음'}"
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
                RETURN h.name AS herb, collect(DISTINCT s.name) AS symptoms
                """,
                name=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'에 대한 치료 증상 정보가 없습니다."
            ss = [x for x in (rec["symptoms"] or []) if x]
            return f"약재: {rec['herb']}\n치료/관련 증상: {', '.join(ss) if ss else '없음'}"
        if sym:
            result = await session.run(
                """
                MATCH (h:Herb)-[:TREATS]->(s:Symptom)
                WHERE s.name = $sname
                RETURN collect(DISTINCT h.name) AS herbs, s.name AS symptom
                """,
                sname=sym,
            )
            rec = await result.single()
            if not rec or not rec["symptom"]:
                return f"증상 '{sym}'에 쓰이는 약재를 찾지 못했습니다."
            herbs = [x for x in (rec["herbs"] or []) if x]
            return f"증상: {rec['symptom']}\n해당 약재: {', '.join(herbs) if herbs else '없음'}"
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
                RETURN f.name AS formula, collect(DISTINCT h.name) AS herbs
                """,
                fname=formula,
            )
            rec = await result.single()
            if not rec or not rec["formula"]:
                return f"처방 '{formula}'를 찾지 못했습니다."
            herbs = [x for x in (rec["herbs"] or []) if x]
            return f"처방: {rec['formula']}\n포함 약재: {', '.join(herbs) if herbs else '없음'}"
        if herb:
            result = await session.run(
                """
                MATCH (f:Formula)-[:CONTAINS]->(h:Herb)
                WHERE h.name = $hname OR $hname IN coalesce(h.synonyms, [])
                RETURN h.name AS herb, collect(DISTINCT f.name) AS formulas
                """,
                hname=herb,
            )
            rec = await result.single()
            if not rec or not rec["herb"]:
                return f"약재 '{herb}'가 포함된 처방을 찾지 못했습니다."
            fs = [x for x in (rec["formulas"] or []) if x]
            return f"약재: {rec['herb']}\n포함된 처방: {', '.join(fs) if fs else '없음'}"
        return "SEARCH_FORMULA_CONTAINS: Formula 또는 Herb 노드가 필요합니다."


async def _tpl_search_contraindication(driver: Any, nodes: list[ExtractedNode]) -> str:
    herbs = _all_herb_names(nodes)
    if not herbs:
        return "SEARCH_CONTRAINDICATION: Herb 노드가 필요합니다."
    hname = herbs[0]
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(
            """
            MATCH (h:Herb)-[:CONTRAINDICATES]->(c:Herb)
            WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
            RETURN h.name AS herb, collect(DISTINCT c.name) AS contra
            """,
            name=hname,
        )
        rec = await result.single()
        if not rec or not rec["herb"]:
            return f"약재 '{hname}'에 대한 상극/금기 정보가 없습니다."
        cs = [x for x in (rec["contra"] or []) if x]
        return f"약재: {rec['herb']}\n상극/금기 약재: {', '.join(cs) if cs else '없음'}"


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
        lines = [f"[유통 요약] 약재: {herb}"]
        if not rows:
            return f"약재 '{herb}'에 연결된 Product가 없습니다."
        for r in rows:
            parts = [f"  상품ID={r['product_id']}", f"유형={r['type']}"]
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
            if r["price_per_geun"] is None:
                continue
            any_p = True
            extra = f", 제조사={r['maker']}" if r["maker"] else ""
            lines.append(
                f"  {r['product_id']}: 근당 {r['price_per_geun']}원 ({r['month']}){extra}"
            )
        if not any_p:
            lines.append("  (가격 이력 없음)")
        return "\n".join(lines)


async def _tpl_search_herb_by_maker(driver: Any, nodes: list[ExtractedNode]) -> str:
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
                RETURN DISTINCT h.name AS herb, p.product_id AS product_id
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
                RETURN DISTINCT h.name AS herb, p.product_id AS product_id
                ORDER BY h.name, product_id
                LIMIT 80
                """,
                mname=maker,
            )
        rows = [r async for r in result]
        if not rows:
            return f"제조사 '{maker}'에 해당하는 약재/상품을 찾지 못했습니다."
        herbs = sorted({r["herb"] for r in rows if r["herb"]})
        return f"제조사: {maker}\n관련 약재: {', '.join(herbs)}"


async def _tpl_search_herb_by_origin(driver: Any, nodes: list[ExtractedNode]) -> str:
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
                RETURN DISTINCT h.name AS herb, p.product_id AS product_id
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
                RETURN DISTINCT h.name AS herb, p.product_id AS product_id
                ORDER BY h.name, product_id
                LIMIT 80
                """,
                oname=origin,
            )
        rows = [r async for r in result]
        if not rows:
            return f"원산지 '{origin}'에 해당하는 약재/상품을 찾지 못했습니다."
        herbs = sorted({r["herb"] for r in rows if r["herb"]})
        return f"원산지: {origin}\n관련 약재: {', '.join(herbs)}"


async def _tpl_search_price_info(driver: Any, nodes: list[ExtractedNode]) -> str:
    herb = _first_name(nodes, "Herb")
    if not herb:
        return "SEARCH_PRICE_INFO: Herb 노드가 필요합니다."
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(
            """
            MATCH (h:Herb)-[:HAS_PRODUCT]->(p:Product)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
            WHERE h.name = $name OR $name IN coalesce(h.synonyms, [])
            OPTIONAL MATCH (p)-[:MANUFACTURED_BY]->(mk:Maker)
            RETURN p.product_id AS product_id, p.type AS type,
                   p.pack_unit AS pack_unit, p.box_qty AS box_qty,
                   pr.month AS month, pr.price_per_geun AS price_per_geun, pr.status AS status,
                   mk.name AS maker
            ORDER BY p.product_id, pr.month DESC
            LIMIT 120
            """,
            name=herb,
        )
        rows = [r async for r in result]
        if not rows:
            return f"약재 '{herb}'의 가격 이력(PriceRecord)이 없습니다."
        lines = [f"[가격 이력] 약재: {herb}"]
        for r in rows:
            if r["price_per_geun"] is None:
                continue
            m = r["maker"] or ""
            pack = f" 포장단위={r['pack_unit']}" if r["pack_unit"] else ""
            box = f" 박스수량={r['box_qty']}" if r["box_qty"] else ""
            lines.append(
                f"  {r['product_id']} ({r['type']}): {r['month']} 근당 {r['price_per_geun']}원 "
                f"({r['status']}) 제조사={m}{pack}{box}"
            )
        return "\n".join(lines) if len(lines) > 1 else lines[0]


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
