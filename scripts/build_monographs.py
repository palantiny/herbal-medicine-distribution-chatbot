"""
모노그래프 빌더 — server2/monograph/*.txt → app/data/herb_monographs.json

처리 흐름:
1. monograph/ 디렉터리의 .txt 파일 스캔 (파일명 = 약재명).
2. 각 파일에서 "2. 약성"부터 "3. 기원" 직전까지 슬라이스 (휴리스틱).
3. 슬라이스된 텍스트를 gpt-4o-mini structured output으로 정제.
4. 결과 dict를 약재명을 키로 저장.

옵션:
  --force      : 이미 JSON에 있는 약재도 재처리.
  --limit N    : 앞 N개 약재만 처리 (디버깅).
  --only NAME  : 특정 약재 1개만 처리.

실행: python scripts/build_monographs.py [--force] [--limit N] [--only 감초]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
MONO_DIR = ROOT / "monograph"
OUT_PATH = ROOT / "app" / "data" / "herb_monographs.json"


class Monograph(BaseModel):
    name_kr: str = Field(description="약재명 (한국어)")
    name_latin: str = Field(default="", description="라틴 학명/약재명")
    sungmi: str = Field(default="", description="성미 (예: '甘平' / '감(甘), 평(平)')")
    guigyeong: list[str] = Field(default_factory=list, description="귀경 (장부 단위, 예: ['비','위','폐','심'])")
    hyoneung: list[str] = Field(default_factory=list, description="효능 (예: ['보비익기','청열해독'])")
    juchi: str = Field(default="", description="주치 (한 문장 또는 쉼표 구분)")
    yongryang: str = Field(default="", description="용량 (예: '2~12g, 大劑量은 15~30g')")
    geumgi: str = Field(default="", description="금기 / 배합금기")
    chejil: str = Field(default="", description="체질배속 (예: '少陰人藥')")
    note: str = Field(default="", description="기타 비고 (없으면 빈 문자열)")


_SYSTEM_PROMPT = """\
당신은 한약재 모노그래프 정제기입니다.
입력으로 받은 텍스트는 한약자원 모노그래프(I)에서 PDF로부터 추출된 raw 텍스트로,
페이지 마커·표 깨짐·각주 번호 등 noise를 포함합니다.

다음 필드를 추출하세요. 정보가 없으면 빈 문자열/빈 배열로 두세요.
- name_kr      : 약재명 (한국어)
- name_latin   : 라틴 학명 또는 라틴 약재명 (예: "Glycyrrhizae Radix et Rhizoma")
- sungmi       : 성미 (한자 그대로 또는 한글 풀이)
- guigyeong    : 귀경. 장부 1글자 단위로 분리한 배열 (예: ["비","위","폐","심"])
- hyoneung     : 효능. 한자 항목 단위로 분리한 배열 (예: ["보비익기","청열해독"])
- juchi        : 주치. 한 줄로 정리. 한자가 있으면 한자 그대로.
- yongryang    : 용량 정보를 한 줄로 정리.
- geumgi       : 금기/배합금기. 한 줄로 정리.
- chejil       : 체질배속 (예: "少陰人藥"). 정보 없으면 빈 문자열.
- note         : 위에 분류되지 않는 중요한 비고가 있으면 한 줄로. 없으면 빈 문자열.

각주 번호(예: "1)", "2)") 같은 raw 메타데이터는 제거하세요.
원문에 없는 정보를 추측해서 채우지 마세요.
"""


def slice_yaksung_section(text: str, herb_name: str) -> str:
    """'2. 약성'부터 '3. 기원' 직전까지 슬라이스. 실패 시 처음 6000자.

    TOC 엔트리(예: '2. 약성·········· 31')는 '·'이 뒤따르므로 negative lookahead로 제외.
    """
    m_start = re.search(r"2\.\s*약성(?!·)", text)
    m_end = re.search(r"3\.\s*기원(?!·)", text)
    if m_start and m_end and m_end.start() > m_start.start():
        return text[m_start.start():m_end.start()]
    if m_start:
        return text[m_start.start():m_start.start() + 6000]
    logger.warning("'%s': '2. 약성' 헤더를 찾지 못함, 처음 6000자 사용", herb_name)
    return text[:6000]


async def process_file(client: AsyncOpenAI, txt_path: Path) -> tuple[str, dict] | None:
    herb_name = unicodedata.normalize("NFC", txt_path.stem)
    raw = txt_path.read_text(encoding="utf-8")
    sliced = slice_yaksung_section(raw, herb_name)

    user_content = f"[약재명] {herb_name}\n\n[원문 추출]\n{sliced}"
    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=Monograph,
            temperature=0.0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            logger.warning("'%s': parsed=None", herb_name)
            return None
        if parsed.name_kr != herb_name:
            logger.info("'%s': name_kr 보정 (%s → %s)", herb_name, parsed.name_kr, herb_name)
            parsed.name_kr = herb_name
        return herb_name, parsed.model_dump()
    except Exception as e:
        logger.exception("'%s' 처리 실패: %s", herb_name, e)
        return None


def load_existing() -> dict:
    if not OUT_PATH.exists():
        return {"_comment": "약재 모노그래프 사전. 키는 정규화된 약재명. scripts/build_monographs.py로 생성."}
    return json.loads(OUT_PATH.read_text(encoding="utf-8"))


def save(data: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def main(force: bool, limit: int | None, only: str | None) -> None:
    client = AsyncOpenAI()
    existing = load_existing()
    files = sorted(MONO_DIR.glob("*.txt"))
    if only:
        only_nfd = unicodedata.normalize("NFD", only)
        only_nfc = unicodedata.normalize("NFC", only)
        files = [f for f in files if f.stem in (only, only_nfd, only_nfc)]
        if not files:
            logger.error("'%s' .txt 파일을 찾지 못했습니다", only)
            return
    if limit:
        files = files[:limit]

    targets = []
    for f in files:
        stem_nfc = unicodedata.normalize("NFC", f.stem)
        if not force and stem_nfc in existing and not stem_nfc.startswith("_"):
            logger.info("skip (이미 처리됨): %s", stem_nfc)
            continue
        targets.append(f)

    logger.info("처리 대상: %d개 (전체 %d개 중)", len(targets), len(files))
    if not targets:
        return

    sem = asyncio.Semaphore(5)

    async def guarded(f):
        async with sem:
            return await process_file(client, f)

    results = await asyncio.gather(*[guarded(f) for f in targets])
    success = 0
    for r in results:
        if r is None:
            continue
        name, mono = r
        existing[name] = mono
        success += 1
        logger.info("ok: %s", name)

    save(existing)
    logger.info("완료: %d/%d 저장 → %s", success, len(targets), OUT_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="이미 처리된 약재 재처리")
    parser.add_argument("--limit", type=int, default=None, help="앞 N개만 처리")
    parser.add_argument("--only", type=str, default=None, help="특정 약재 1개만 처리")
    args = parser.parse_args()
    asyncio.run(main(args.force, args.limit, args.only))
