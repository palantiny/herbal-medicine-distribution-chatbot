"""
DJMEDI API 응답 스펙 검증 + 실제 제조사 목록 산출.

실행: python scripts/verify_djmedi_api.py [cfcode]
산출: scripts/output/djmedi_verify_report.json + 콘솔 출력

검증 항목:
1. herbmaker     : list[].mk_code, mk_name 존재 여부
2. herbmedicine  : list[].md_code, md_medi, md_name, mk_code, mk_name 존재 여부
                   (첫 mk_code 1건으로 sample 호출)
3. membermedicine: cfcode 인자가 주어지면 첫 약재의 md_medi로 호출 →
                   md_code, md_medi, md_name, mm_medicine, mm_name, mm_origin, mk_code, mk_name 검증

코드 측 사용 필드와의 차이가 발견되면 콘솔에 경고로 출력.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ["DJMEDI_API_BASE_URL"]
AUTH_KEY = os.environ["DJMEDI_AUTH_KEY"]

# 코드(djmedi_service.py)에서 사용 중인 필드 (검증 기준)
EXPECTED_FIELDS = {
    "herbmaker": {"mk_code", "mk_name"},
    "herbmedicine": {"md_code", "md_medi", "md_name", "mk_code", "mk_name"},
    "membermedicine": {
        "md_code", "md_medi", "md_name",
        "mm_medicine", "mm_name", "mm_origin",
        "mk_code", "mk_name",
    },
}


async def _call(params: dict[str, str]) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(BASE_URL, params=params, headers={"cfauthkey": AUTH_KEY})
        r.raise_for_status()
        return r.json()


def _check_fields(api_code: str, items: list[dict]) -> dict:
    if not items:
        return {"sample_count": 0, "missing": [], "extra": []}
    keys_in_first = set(items[0].keys())
    expected = EXPECTED_FIELDS[api_code]
    missing = sorted(expected - keys_in_first)
    extra = sorted(keys_in_first - expected)
    return {
        "sample_count": len(items),
        "first_item_keys": sorted(keys_in_first),
        "missing": missing,
        "extra": extra,
    }


async def main(cfcode: str | None = None) -> None:
    report: dict = {"base_url": BASE_URL, "results": {}}

    # 1. herbmaker
    print("\n[1] herbmaker")
    data = await _call({"apiCode": "herbmaker", "language": "kor"})
    items = data.get("list") or []
    print(f"  resultCode={data.get('resultCode')} count={len(items)}")
    report["results"]["herbmaker"] = {
        "resultCode": data.get("resultCode"),
        "field_check": _check_fields("herbmaker", items),
        "makers": [{"mk_code": m.get("mk_code"), "mk_name": m.get("mk_name")} for m in items],
    }
    fc = report["results"]["herbmaker"]["field_check"]
    if fc["missing"]:
        print(f"  ⚠️  missing fields: {fc['missing']}")
    if fc["extra"]:
        print(f"  ℹ️  extra fields: {fc['extra']}")
    print("  실제 제조사 목록:")
    for m in items:
        print(f"    - {m.get('mk_code')} {m.get('mk_name')}")

    # 2. herbmedicine — 첫 제조사로 sample
    if items:
        sample_mk = items[0]["mk_code"]
        print(f"\n[2] herbmedicine (sample mk_code={sample_mk})")
        data = await _call({"apiCode": "herbmedicine", "language": "kor", "search": sample_mk})
        meds = data.get("list") or []
        print(f"  resultCode={data.get('resultCode')} count={len(meds)}")
        report["results"]["herbmedicine"] = {
            "sample_mk_code": sample_mk,
            "resultCode": data.get("resultCode"),
            "field_check": _check_fields("herbmedicine", meds),
            "first_item": meds[0] if meds else None,
        }
        fc = report["results"]["herbmedicine"]["field_check"]
        if fc["missing"]:
            print(f"  ⚠️  missing fields: {fc['missing']}")

        # 3. membermedicine — cfcode 인자가 있고 첫 약재가 있으면 sample
        if cfcode and meds:
            sample_md_medi = meds[0].get("md_medi")
            print(f"\n[3] membermedicine (cfcode={cfcode}, search={sample_md_medi})")
            data = await _call({
                "apiCode": "membermedicine",
                "language": "kor",
                "search": sample_md_medi,
                "cfcode": cfcode,
            })
            mems = data.get("list") or []
            print(f"  resultCode={data.get('resultCode')} count={len(mems)}")
            report["results"]["membermedicine"] = {
                "sample_md_medi": sample_md_medi,
                "sample_cfcode": cfcode,
                "resultCode": data.get("resultCode"),
                "field_check": _check_fields("membermedicine", mems),
                "first_item": mems[0] if mems else None,
            }
            fc = report["results"]["membermedicine"]["field_check"]
            if fc["missing"]:
                print(f"  ⚠️  missing fields: {fc['missing']}")
        else:
            print("\n[3] membermedicine — cfcode 미제공 또는 약재 0건, 건너뜀")

    out_path = Path(__file__).parent / "output" / "djmedi_verify_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n리포트 저장: {out_path}")


if __name__ == "__main__":
    cfcode = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(cfcode))
