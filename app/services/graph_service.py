"""
한약재 지식 그래프 서비스 (Neo4j)
"""
import logging
from typing import Any

from neo4j import AsyncGraphDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Neo4j 드라이버 (싱글톤) ──────────────────────────
_driver = None


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


# ── Neo4j 쿼리 ───────────────────────────────────────
async def _query_neo4j(herb_name: str) -> str | None:
    """Neo4j에서 약재 정보 + 관계 조회."""
    driver = await get_neo4j_driver()
    if not driver:
        return None

    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                """
                MATCH (h:Herb)
                WHERE h.name = $name OR $name IN h.synonyms
                OPTIONAL MATCH (h)-[:HAS_EFFICACY]->(e:Efficacy)
                OPTIONAL MATCH (h)-[:HAS_TEMP]->(t:NatureTemp)
                OPTIONAL MATCH (h)-[:HAS_TASTE]->(taste:NatureTaste)
                OPTIONAL MATCH (h)-[:TREATS]->(s:Symptom)
                OPTIONAL MATCH (h)-[:ACTS_ON]->(m:Meridian)
                OPTIONAL MATCH (h)-[:CONTRAINDICATES]->(c:Herb)
                RETURN h.name AS name,
                       h.toxicity AS toxicity,
                       h.synonyms AS synonyms,
                       COLLECT(DISTINCT e.name) AS efficacies,
                       COLLECT(DISTINCT t.name) AS natures,
                       COLLECT(DISTINCT taste.name) AS tastes,
                       COLLECT(DISTINCT s.name) AS symptoms,
                       COLLECT(DISTINCT m.name) AS meridians,
                       COLLECT(DISTINCT c.name) AS contraindications
                """,
                name=herb_name,
            )
            record = await result.single()

            if not record or not record["name"]:
                return None

            lines = [f"한약재: {record['name']}"]
            synonyms = [s for s in (record["synonyms"] or []) if s and s != record["name"]]
            if synonyms:
                lines.append(f"이명: {', '.join(synonyms)}")
            if record["toxicity"]:
                lines.append(f"독성: {record['toxicity']}")
            efficacies = [e for e in record["efficacies"] if e]
            if efficacies:
                lines.append(f"효능: {', '.join(efficacies)}")
            natures = [n for n in record["natures"] if n]
            if natures:
                lines.append(f"성질: {', '.join(natures)}")
            tastes = [t for t in record["tastes"] if t]
            if tastes:
                lines.append(f"맛: {', '.join(tastes)}")
            meridians = [m for m in record["meridians"] if m]
            if meridians:
                lines.append(f"귀경: {', '.join(meridians)}")
            symptoms = [s for s in record["symptoms"] if s]
            if symptoms:
                lines.append(f"치료 증상: {', '.join(symptoms)}")
            contraindications = [c for c in record["contraindications"] if c]
            if contraindications:
                lines.append(f"금기: {', '.join(contraindications)}")

            # 가격 정보 조회
            price_result = await session.run(
                """
                MATCH (h:Herb)-[:HAS_PRODUCT]->(p:Product)-[:HAS_PRICE_HISTORY]->(pr:PriceRecord)
                WHERE (h.name = $name OR $name IN h.synonyms)
                WITH p, pr ORDER BY pr.month DESC
                WITH p, COLLECT(pr)[0] AS latest
                OPTIONAL MATCH (p)-[:MANUFACTURED_BY]->(mk:Maker)
                OPTIONAL MATCH (p)-[:ORIGINATES_FROM]->(o:Origin)
                RETURN p.product_id AS product_id,
                       p.type AS type,
                       p.pack_unit AS pack_unit,
                       p.pack_price AS pack_price,
                       p.box_qty AS box_qty,
                       latest.month AS month,
                       latest.price_per_geun AS price_per_geun,
                       latest.status AS status,
                       mk.name AS maker,
                       o.name AS origin
                ORDER BY p.product_id
                """,
                name=herb_name,
            )
            price_records = [r async for r in price_result]
            if price_records:
                lines.append("\n[가격 정보]")
                for pr in price_records:
                    if not pr["price_per_geun"]:
                        continue
                    parts = [f"  [product_id={pr['product_id']}] {pr['type'] or ''}"]
                    if pr["maker"]:
                        parts.append(f"제조사={pr['maker']}")
                    if pr["origin"]:
                        parts.append(f"원산지={pr['origin']}")
                    parts.append(f"근당={pr['price_per_geun']}원")
                    if pr["pack_unit"] and pr["pack_price"]:
                        parts.append(f"포장={pr['pack_unit']}g/{pr['pack_price']}원")
                    if pr["month"]:
                        parts.append(f"({pr['month']} 기준)")
                    lines.append(", ".join(parts))

            return "\n".join(lines)
    except Exception as e:
        logger.exception("Neo4j 쿼리 실패: %s", e)
        return None


async def _search_neo4j_all(query: str) -> str | None:
    """Neo4j에서 query에 포함된 약재 또는 전체 목록 조회."""
    driver = await get_neo4j_driver()
    if not driver:
        return None

    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                """
                MATCH (h:Herb)
                WHERE h.name CONTAINS $keyword OR ANY(s IN h.synonyms WHERE s CONTAINS $keyword)
                OPTIONAL MATCH (h)-[:HAS_EFFICACY]->(e:Efficacy)
                RETURN h.name AS name, COLLECT(DISTINCT e.name) AS efficacies
                LIMIT 10
                """,
                keyword=query,
            )
            records = [r async for r in result]

            if not records:
                result = await session.run(
                    "MATCH (h:Herb) RETURN h.name AS name ORDER BY h.name LIMIT 50"
                )
                names = [r["name"] async for r in result]
                if names:
                    return f"등록된 한약재: {', '.join(names)}. 특정 한약재 이름을 말씀해 주시면 자세히 안내해 드리겠습니다."
                return None

            lines = []
            for r in records:
                efficacies = [e for e in r["efficacies"] if e]
                eff_str = f": 효능={', '.join(efficacies)}" if efficacies else ""
                lines.append(f"{r['name']}{eff_str}")
            return "\n".join(lines)
    except Exception as e:
        logger.exception("Neo4j 전체 검색 실패: %s", e)
        return None


# ── 외부 인터페이스 ──────────────────────────────────
async def search_herb_graph(query: str, extracted_entities: dict[str, Any] | None = None) -> str:
    """
    한약재 지식 그래프 탐색 (Neo4j).
    """
    herb_name = None
    if extracted_entities and extracted_entities.get("herb_name"):
        herb_name = extracted_entities["herb_name"]

    # Neo4j 조회
    if herb_name:
        neo4j_result = await _query_neo4j(herb_name)
        if neo4j_result:
            return neo4j_result
        return f"'{herb_name}'에 대한 지식 그래프 정보가 없습니다."

    neo4j_result = await _search_neo4j_all(query)
    if neo4j_result:
        return neo4j_result

    return "지식 그래프에서 관련 정보를 찾지 못했습니다. 특정 한약재 이름을 말씀해 주시면 자세히 안내해 드리겠습니다."
