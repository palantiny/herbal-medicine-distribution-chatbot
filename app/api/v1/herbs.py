"""
Herbs API — PostgreSQL에서 약재 목록/상세 조회
GET /herbs         : 전체 약재 목록 (han_medicine + price 테이블 조인)
GET /herbs/{herb_id} : 약재 상세 정보
"""
import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.database import async_session_maker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/herbs", tags=["herbs"])


def _row_to_dict(row) -> dict:
    """SQLAlchemy Row → dict 변환."""
    return dict(row._mapping)


@router.get("")
async def get_herbs():
    """
    전체 약재 목록 조회.
    han_medicine 테이블을 기반으로, price_domestic/price_imported에서 가격 정보를 보충.
    """
    async with async_session_maker() as session:
        # han_medicine에서 기본 정보 조회
        result = await session.execute(text("""
            SELECT
                hm.md_seq AS id,
                TRIM(hm.md_title_kor) AS name,
                COALESCE(TRIM(hm.md_title_chn), '') AS name_chn,
                COALESCE(TRIM(hm.md_title_eng), '') AS name_eng,
                COALESCE(TRIM(hm.md_origin_kor), '') AS origin,
                COALESCE(hm.md_price, 0) AS price,
                COALESCE(hm.md_qty, 0) AS qty,
                COALESCE(hm.md_status, 'use') AS status,
                COALESCE(TRIM(hm.md_desc_kor), '') AS description,
                COALESCE(TRIM(hm.md_feature_kor), '') AS feature,
                COALESCE(TRIM(hm.md_note_kor), '') AS note,
                COALESCE(TRIM(hm.md_interact_kor), '') AS interaction,
                COALESCE(TRIM(hm.md_relate_kor), '') AS related,
                COALESCE(TRIM(hm.md_property_kor), '') AS property,
                hm.herb_id AS herb_id
            FROM han_medicine hm
            WHERE hm.md_title_kor IS NOT NULL
              AND TRIM(hm.md_title_kor) != ''
            ORDER BY hm.md_title_kor
        """))
        medicines = [_row_to_dict(row) for row in result]

        # price 테이블에서 가격 정보 가져오기 (각각 조회 후 합침 - 타입 불일치 방지)
        _price_sql = """
            SELECT
                "약재명" AS herb_name,
                "원산지" AS origin,
                "구분" AS grade,
                CAST("근당 가격" AS text) AS price_per_geun,
                CAST("포장 단위(g)" AS text) AS packaging_unit_g,
                CAST("포장 단위 당 가격" AS text) AS packaging_unit_price,
                CAST("박스 수량" AS text) AS box_quantity,
                CAST("구독 가격" AS text) AS subscription_price,
                "제약사" AS manufacturer,
                "비고" AS note,
                CAST("구독 구매 할인율" AS text) AS discount_rate,
                market_type
            FROM {table}
        """
        dom_result = await session.execute(text(_price_sql.replace("{table}", "price_domestic")))
        imp_result = await session.execute(text(_price_sql.replace("{table}", "price_imported")))
        prices = [_row_to_dict(row) for row in dom_result] + [_row_to_dict(row) for row in imp_result]

        # 약재명 → 가격 정보 매핑 (첫 번째 매칭)
        price_map: dict[str, dict] = {}
        for p in prices:
            name = str(p.get("herb_name", "")).strip()
            if name and name not in price_map:
                price_map[name] = p

        # 결과 조합
        herbs = []
        for med in medicines:
            name = med["name"]
            price_info = price_map.get(name, {})

            # 재고 상태 계산
            qty = med.get("qty", 0)
            try:
                qty = int(qty) if qty else 0
            except (ValueError, TypeError):
                qty = 0

            if med.get("status") == "soldout" or qty <= 0:
                stock_status = "out"
            elif qty < 10:
                stock_status = "low"
            elif qty < 50:
                stock_status = "medium"
            else:
                stock_status = "high"

            # 가격 결정: price 테이블 우선, 없으면 han_medicine의 md_price
            display_price = 0
            if price_info.get("packaging_unit_price"):
                try:
                    display_price = int(float(str(price_info["packaging_unit_price"]).replace(",", "")))
                except (ValueError, TypeError):
                    pass
            if not display_price and med.get("price"):
                try:
                    display_price = int(float(str(med["price"]).replace(",", "")))
                except (ValueError, TypeError):
                    pass

            # 원산지 결정
            origin = med.get("origin", "")
            if not origin and price_info.get("origin"):
                origin = str(price_info["origin"]).strip()

            herbs.append({
                "id": str(med["id"]),
                "name": name,
                "name_chn": med.get("name_chn", ""),
                "name_eng": med.get("name_eng", ""),
                "origin": origin,
                "price": display_price,
                "stockStatus": stock_status,
                "qty": qty,
                "description": med.get("description", ""),
                "feature": med.get("feature", ""),
                "note": med.get("note", ""),
                "interaction": med.get("interaction", ""),
                "related": med.get("related", ""),
                "property": med.get("property", ""),
                "manufacturer": str(price_info.get("manufacturer", "")).strip() if price_info.get("manufacturer") else "",
                "packagingUnitG": str(price_info.get("packaging_unit_g", "")).strip() if price_info.get("packaging_unit_g") else "",
                "boxQuantity": str(price_info.get("box_quantity", "")).strip() if price_info.get("box_quantity") else "",
                "subscriptionPrice": str(price_info.get("subscription_price", "")).strip() if price_info.get("subscription_price") else "",
                "discountRate": str(price_info.get("discount_rate", "")).strip() if price_info.get("discount_rate") else "",
                "grade": str(price_info.get("grade", "")).strip() if price_info.get("grade") else "",
                "marketType": str(price_info.get("market_type", "")).strip() if price_info.get("market_type") else "",
            })

        return {"herbs": herbs, "total": len(herbs)}


@router.get("/{herb_id}")
async def get_herb_detail(herb_id: str):
    """
    약재 상세 정보 조회.
    han_medicine + han_medicine_dj + warehouse 정보를 조합.
    """
    async with async_session_maker() as session:
        # 기본 정보
        result = await session.execute(text("""
            SELECT
                hm.md_seq AS id,
                TRIM(hm.md_title_kor) AS name,
                COALESCE(TRIM(hm.md_title_chn), '') AS name_chn,
                COALESCE(TRIM(hm.md_title_eng), '') AS name_eng,
                COALESCE(TRIM(hm.md_origin_kor), '') AS origin,
                COALESCE(hm.md_price, 0) AS price,
                COALESCE(hm.md_qty, 0) AS qty,
                COALESCE(hm.md_status, 'use') AS status,
                COALESCE(TRIM(hm.md_desc_kor), '') AS description,
                COALESCE(TRIM(hm.md_feature_kor), '') AS feature,
                COALESCE(TRIM(hm.md_note_kor), '') AS note,
                COALESCE(TRIM(hm.md_interact_kor), '') AS interaction,
                COALESCE(TRIM(hm.md_relate_kor), '') AS related,
                COALESCE(TRIM(hm.md_property_kor), '') AS property,
                hm.md_code AS code,
                hm.herb_id AS herb_id
            FROM han_medicine hm
            WHERE hm.md_seq = :herb_id
        """), {"herb_id": int(herb_id)})
        row = result.first()

        if not row:
            raise HTTPException(status_code=404, detail="약재를 찾을 수 없습니다.")

        med = _row_to_dict(row)
        name = med["name"]

        # price 테이블에서 가격 정보 (각각 조회 - 타입 불일치 방지)
        _detail_price_sql = """
            SELECT
                "약재명" AS herb_name,
                "원산지" AS origin,
                "구분" AS grade,
                CAST("근당 가격" AS text) AS price_per_geun,
                CAST("포장 단위(g)" AS text) AS packaging_unit_g,
                CAST("포장 단위 당 가격" AS text) AS packaging_unit_price,
                CAST("박스 수량" AS text) AS box_quantity,
                CAST("구독 가격" AS text) AS subscription_price,
                "제약사" AS manufacturer,
                "비고" AS note,
                CAST("구독 구매 할인율" AS text) AS discount_rate,
                market_type
            FROM {table}
            WHERE TRIM("약재명") = :name
            LIMIT 1
        """
        price_row = None
        for tbl in ["price_domestic", "price_imported"]:
            pr = await session.execute(text(_detail_price_sql.replace("{table}", tbl)), {"name": name})
            price_row = pr.first()
            if price_row:
                break
        price_info = _row_to_dict(price_row) if price_row else {}

        # han_medicine_dj에서 추가 정보 (성, 미, 귀경, 사상)
        dj_result = await session.execute(text("""
            SELECT
                COALESCE(TRIM(mm_state), '') AS nature,
                COALESCE(TRIM(mm_taste), '') AS taste,
                COALESCE(TRIM(mm_object), '') AS meridian,
                COALESCE(TRIM(mm_feature), '') AS constitution,
                COALESCE(TRIM(mm_origin_kor), '') AS dj_origin,
                COALESCE(mm_price, 0) AS dj_price,
                COALESCE(mm_qty, 0) AS dj_qty
            FROM han_medicine_dj
            WHERE TRIM(SPLIT_PART(mm_title_kor, '(', 1)) = :name
            LIMIT 1
        """), {"name": name})
        dj_row = dj_result.first()
        dj_info = _row_to_dict(dj_row) if dj_row else {}

        # warehouse에서 최근 입고 정보
        wh_result = await session.execute(text("""
            SELECT
                COALESCE(TRIM(wh_maker), '') AS warehouse_maker,
                COALESCE(TRIM(wh_origin), '') AS warehouse_origin,
                COALESCE(wh_date, '') AS warehouse_date,
                COALESCE(wh_expired, '') AS warehouse_expired,
                COALESCE(wh_qty, 0) AS warehouse_qty,
                COALESCE(wh_price, 0) AS warehouse_price
            FROM han_warehouse
            WHERE TRIM(wh_title) = :name
            ORDER BY wh_date DESC
            LIMIT 1
        """), {"name": name})
        wh_row = wh_result.first()
        wh_info = _row_to_dict(wh_row) if wh_row else {}

        # 가격 결정
        display_price = 0
        if price_info.get("packaging_unit_price"):
            try:
                display_price = int(float(str(price_info["packaging_unit_price"]).replace(",", "")))
            except (ValueError, TypeError):
                pass
        if not display_price and med.get("price"):
            try:
                display_price = int(float(str(med["price"]).replace(",", "")))
            except (ValueError, TypeError):
                pass

        # 재고 상태
        qty = med.get("qty", 0)
        try:
            qty = int(qty) if qty else 0
        except (ValueError, TypeError):
            qty = 0

        if med.get("status") == "soldout" or qty <= 0:
            stock_status = "out"
        elif qty < 10:
            stock_status = "low"
        elif qty < 50:
            stock_status = "medium"
        else:
            stock_status = "high"

        origin = med.get("origin", "")
        if not origin and price_info.get("origin"):
            origin = str(price_info["origin"]).strip()

        return {
            "id": str(med["id"]),
            "name": name,
            "name_chn": med.get("name_chn", ""),
            "name_eng": med.get("name_eng", ""),
            "origin": origin,
            "price": display_price,
            "stockStatus": stock_status,
            "qty": qty,
            "status": med.get("status", ""),
            "description": med.get("description", ""),
            "feature": med.get("feature", ""),
            "note": med.get("note", ""),
            "interaction": med.get("interaction", ""),
            "related": med.get("related", ""),
            "property": med.get("property", ""),
            "code": med.get("code", ""),
            # price info
            "manufacturer": str(price_info.get("manufacturer", "")).strip() if price_info.get("manufacturer") else "",
            "packagingUnitG": str(price_info.get("packaging_unit_g", "")).strip() if price_info.get("packaging_unit_g") else "",
            "pricePerGeun": str(price_info.get("price_per_geun", "")).strip() if price_info.get("price_per_geun") else "",
            "boxQuantity": str(price_info.get("box_quantity", "")).strip() if price_info.get("box_quantity") else "",
            "subscriptionPrice": str(price_info.get("subscription_price", "")).strip() if price_info.get("subscription_price") else "",
            "discountRate": str(price_info.get("discount_rate", "")).strip() if price_info.get("discount_rate") else "",
            "grade": str(price_info.get("grade", "")).strip() if price_info.get("grade") else "",
            "marketType": str(price_info.get("market_type", "")).strip() if price_info.get("market_type") else "",
            # han_medicine_dj info
            "nature": dj_info.get("nature", ""),
            "taste": dj_info.get("taste", ""),
            "meridian": dj_info.get("meridian", ""),
            "constitution": dj_info.get("constitution", ""),
            # warehouse info
            "warehouseMaker": wh_info.get("warehouse_maker", ""),
            "warehouseOrigin": wh_info.get("warehouse_origin", ""),
            "warehouseDate": str(wh_info.get("warehouse_date", "")),
            "warehouseExpired": str(wh_info.get("warehouse_expired", "")),
        }
