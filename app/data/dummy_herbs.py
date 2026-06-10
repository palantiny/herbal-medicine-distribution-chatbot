"""
한약재 더미데이터 (server1 figma 더미와 동일한 12종).

챗봇이 가격·원산지·제조사·재고·배송 등을 더미데이터로 답하고,
장바구니 담기(약재명 → id 매핑)에 사용한다.
효능·성미·귀경은 herb_monographs.json(monograph_service)에서 별도 조회.
"""
from __future__ import annotations

# 공통 배송 정보 (figma ProductDetail 기준)
DELIVERY_FEE = 3000
DELIVERY_INFO = "일반 배송 3,000원, 평균 2-3일 이내 도착"

# 재고 상태 한글 표기
STOCK_LABEL = {"high": "충분", "medium": "보통", "low": "부족", "out": "품절"}

HERBS: list[dict] = [
    {"id": "1", "name": "감초", "price": 48000, "origin": "중국산", "origin_detail": "수입 (중국 내몽고)", "manufacturer": "씨케이(주)", "stock_status": "high", "available_sellers": 16, "weight": "600g", "category": "수입 약재 > 뿌리류", "short_description": "중국 내몽고 지역의 엄선된 감초 뿌리"},
    {"id": "2", "name": "마황", "price": 32000, "origin": "중국산", "origin_detail": "수입 (중국 내몽고)", "manufacturer": "씨케이(주)", "stock_status": "high", "available_sellers": 14, "weight": "450g", "category": "수입 약재 > 전초류", "short_description": "중국 내몽고 지역의 엄선된 마황"},
    {"id": "3", "name": "대복피", "price": 38000, "origin": "인도네시아산", "origin_detail": "수입 (인도네시아)", "manufacturer": "씨케이(주)", "stock_status": "high", "available_sellers": 15, "weight": "600g", "category": "수입 약재 > 껍질류", "short_description": "인도네시아 수마트라 지역 빈랑의 열매껍질"},
    {"id": "4", "name": "복령", "price": 52000, "origin": "국내산", "origin_detail": "국내산 (전라남도)", "manufacturer": "씨케이(주)", "stock_status": "medium", "available_sellers": 10, "weight": "800g", "category": "국내 약재 > 균류", "short_description": "국내 청정지역의 프리미엄 복령"},
    {"id": "5", "name": "백출", "price": 45000, "origin": "중국산", "origin_detail": "수입 (중국 저장성)", "manufacturer": "씨케이(주)", "stock_status": "high", "available_sellers": 12, "weight": "500g", "category": "수입 약재 > 뿌리류", "short_description": "중국 저장성의 엄선된 백출"},
    {"id": "6", "name": "반하생강백반제", "price": 250000, "origin": "중국산", "origin_detail": "수입 (중국)", "manufacturer": "씨케이(주)", "stock_status": "low", "available_sellers": 5, "weight": "100g", "category": "수입 약재 > 가공약재", "short_description": "전통 방식으로 제조한 반하생강백반제"},
    {"id": "7", "name": "용안육", "price": 35000, "origin": "중국산", "origin_detail": "수입 (중국 광둥성)", "manufacturer": "씨케이(주)", "stock_status": "medium", "available_sellers": 13, "weight": "400g", "category": "수입 약재 > 열매류", "short_description": "중국 광둥성의 달콤한 용안육"},
    {"id": "8", "name": "숙지황", "price": 72000, "origin": "중국산", "origin_detail": "수입 (중국 허난성)", "manufacturer": "씨케이(주)", "stock_status": "medium", "available_sellers": 7, "weight": "100g", "category": "수입 약재 > 뿌리류", "short_description": "중국 허난성의 전통 제조 숙지황"},
    {"id": "9", "name": "인삼", "price": 42000, "origin": "국내산", "origin_detail": "국내산 (충청남도 금산)", "manufacturer": "씨케이(주)", "stock_status": "high", "available_sellers": 11, "weight": "500g", "category": "국내 약재 > 뿌리류", "short_description": "금산 6년근 프리미엄 인삼"},
    {"id": "10", "name": "설복령", "price": 33000, "origin": "중국산", "origin_detail": "수입 (중국 윈난성)", "manufacturer": "씨케이(주)", "stock_status": "high", "available_sellers": 12, "weight": "600g", "category": "수입 약재 > 균류", "short_description": "중국 윈난성의 고품질 설복령"},
    {"id": "11", "name": "복분자", "price": 65000, "origin": "국내산", "origin_detail": "국내산 (전라남도 고흥)", "manufacturer": "씨케이(주)", "stock_status": "high", "available_sellers": 9, "weight": "300g", "category": "국내 약재 > 열매류", "short_description": "전라남도 고흥의 청정 복분자"},
    {"id": "12", "name": "백지", "price": 54000, "origin": "국내산", "origin_detail": "국내산 (강원도)", "manufacturer": "씨케이(주)", "stock_status": "medium", "available_sellers": 10, "weight": "400g", "category": "국내 약재 > 뿌리류", "short_description": "강원도 청정지역의 프리미엄 백지"},
]

# 이름 → 약재 dict 빠른 조회
_BY_NAME = {h["name"]: h for h in HERBS}


def find_by_name(name: str) -> dict | None:
    """약재명으로 더미 약재 조회. 정확 매칭 우선, 없으면 포함 매칭."""
    if not name:
        return None
    name = name.strip()
    if name in _BY_NAME:
        return _BY_NAME[name]
    for herb in HERBS:
        if herb["name"] in name or name in herb["name"]:
            return herb
    return None


def format_catalog_for_prompt() -> str:
    """판매 중인 12종 약재를 LLM 프롬프트용 텍스트로 변환."""
    lines = ["[판매 중인 약재 목록 (12종)]"]
    for h in HERBS:
        stock = STOCK_LABEL.get(h["stock_status"], h["stock_status"])
        lines.append(
            f"{h['id']}. {h['name']} — 가격 {h['price']:,}원, 원산지 {h['origin']}({h['origin_detail']}), "
            f"제조사 {h['manufacturer']}, 재고 {stock}, 재고 보유 판매처 {h['available_sellers']}곳, "
            f"중량 {h['weight']}, 분류 {h['category']}, 설명 {h['short_description']}"
        )
    lines.append(f"\n[배송 정보] {DELIVERY_INFO}")
    return "\n".join(lines)
