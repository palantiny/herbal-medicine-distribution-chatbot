# LLM 파이프라인 리팩토링 — Neo4j → DJMEDI API

## 변경 배경

기존 파이프라인은 Neo4j 지식 그래프 + PostgreSQL 로컬 약재 테이블을 기반으로 동작했다.
약재 데이터를 직접 저장·관리하는 대신, DJMEDI 외부 API를 통해 실시간으로 가져오는 구조로 전환하면서 파이프라인 전체를 재설계했다.

---

## 아키텍처 비교

### 이전 구조

```
사용자 질문
  └─ Stage 1 (LLM1 — RouterOutput 구조화 출력)
       ├─ DIRECT_ANSWER        → 즉시 스트리밍
       ├─ SEARCH_GRAPH (루프)  → Neo4j 12개 탐색 템플릿 병렬 실행
       │    └─ 최대 N회 반복 후 GENERATE_FINAL_ANSWER
       ├─ CALL_LLM2_SQL        → Text-to-SQL → PostgreSQL (로컬 약재 테이블)
       └─ GENERATE_FINAL_ANSWER → Stage 3 (LLM3 합성)
```

- 데이터 소스: Neo4j (지식 그래프) + PostgreSQL (han_medicine, han_warehouse, price_domestic 등 로컬 테이블)
- 오케스트레이터: LangGraph `StateGraph` (TypedDict 상태 전달)
- 12가지 Neo4j 탐색 intent (SEARCH_TEMP, SEARCH_TASTE, SEARCH_MERIDIAN, SEARCH_EFFICACY 등)
- 사고과정(Thinking) 스트리밍: `thinking_token` SSE 이벤트 별도 발행

### 현재 구조

```
사용자 질문
  └─ LLM1 엔티티 추출 (gpt-4o-mini)
       └─ BM25 스킴 리졸버 (aliases JSON 기반 엔티티 정규화)
            └─ LLM2 라우팅 (gpt-4o — 구조화 출력 Llm2Output)
                 ├─ DIRECT_ANSWER  → LLM3 (또는 즉시 스트리밍)
                 ├─ SQL            → Redis Queue → sql_worker → LLM3
                 └─ DJMEDI_API     → DJMEDI 외부 API → LLM3
```

- 데이터 소스: DJMEDI 외부 API 전용 (herbmaker / herbmedicine / membermedicine)
- 오케스트레이터: 단순 순차 `async` 함수 (`run_pipeline`)
- 로컬 PostgreSQL: `users` 테이블만 존재 (약재 테이블 없음)

---

## 파일별 변경 내역

### 삭제된 파일

| 파일 | 이유 |
|------|------|
| `app/services/graph_service.py` | Neo4j 연결 및 Cypher 쿼리 실행 전담 — Neo4j 제거로 불필요 |
| `app/services/cache_service.py` | Neo4j/로컬 약재 캐시 서비스 — DJMEDI 서비스 내 캐시로 통합 |
| `app/schemas/stage1_router.py` | RouterOutput, Stage1Route 등 Stage1 구조화 출력 스키마 — 파이프라인 재설계로 불필요 |

### 신규 추가 파일

| 파일 | 역할 |
|------|------|
| `app/services/entity_extractor.py` | LLM1 — gpt-4o-mini로 herb_name / maker / origin / packaging_unit 슬롯 추출 |
| `app/services/scheme_resolver.py` | BM25 — `scheme_aliases.json` 기반 엔티티 표면형 → 정규화명 매핑 |
| `app/services/djmedi_service.py` | DJMEDI API 클라이언트 + Redis 캐시 + `smart_search()` 오케스트레이터 |
| `app/data/scheme_aliases.json` | 약재명 / 제조사명 / 원산지 별칭 목록 (BM25 인덱스 소스) |
| `test_pipeline.py` | 파이프라인 단계별 단독 실행 테스트 스크립트 |

### 대폭 수정된 파일

#### `app/services/pipeline.py`
- **Before**: LangGraph `StateGraph` 6노드 (llm1_extract → scheme_resolve → llm2_route → [direct_answer / execute_sql / execute_djmedi] → llm3_synthesize), TypedDict `PipelineState` 로 상태 전달
- **After**: 단순 순차 `async` 함수 5단계
  - `_step_llm1()` — 엔티티 추출
  - `_step_bm25()` — BM25 정규화
  - `_step_llm2()` — 라우팅 + 쿼리 플래닝
  - `_step_execute()` — DJMEDI API / SQL / DIRECT 분기 실행
  - `_step_llm3()` — 최종 답변 합성 스트리밍
  - `run_pipeline()` 진입점 유지 (`chat_service.py` 인터페이스 불변)

#### `app/utils/prompts.py`
- **Before**: Stage1 RouterOutput 프롬프트 (12개 Neo4j intent 안내), Stage2 Text-to-SQL, Stage3 합성, Thinking 스트리밍 프롬프트, herb-card 카드 형식 규칙
- **After**: `LLM2_SYSTEM_PROMPT` (DJMEDI 4가지 intent 라우팅 기준), `LLM3_SYSTEM_PROMPT` (최종 합성), 공통 `ANTI_HALLUCINATION_DIRECTIVE` / `FORMAT_DIRECTIVE`

#### `app/core/config.py`
- **Removed**: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `NEO4J_QUERY_PARALLEL_MAX`, `STAGE1_GRAPH_MAX_ROUNDS`, `PIPELINE_VERSION`
- **Added**: `DJMEDI_API_BASE_URL`, `DJMEDI_AUTH_KEY`

#### `app/api/v1/cache.py`
- **Before**: `herb:cache:*` 로컬 약재 캐시 관리 (GET 단건 조회 포함)
- **After**: DJMEDI API Redis 캐시 관리
  - `GET /cache/stats` — 캐시 키 수 / 히트율
  - `DELETE /cache/makers` — herbmaker 캐시 무효화
  - `DELETE /cache/medicines` — herbmedicine 전체 무효화
  - `DELETE /cache/members` — membermedicine 전체 무효화
  - `DELETE /cache` — 전체 무효화

#### `app/services/chat_service.py`
- **Before**: v1/v2 분기, `_publish_event()` 헬퍼 내장, `cfcode` 파라미터 없음
- **After**: `run_pipeline()` 직접 호출, `cfcode` 파라미터 전달

#### `app/schemas/__init__.py`
- 삭제된 `stage1_router.py` 참조 제거 (빈 모듈로 정리)

---

## DJMEDI API 연동 구조

```
smart_search(intent, maker_name, herb_name, origin, cfcode)
  ├─ get_maker_list      → herbmaker API   (24h 캐시)
  ├─ get_herb_by_maker   → herbmedicine API (1h 캐시, mk_code로 조회)
  ├─ get_herb_by_name    → 전 제조사 병렬 조회 후 필터
  └─ get_my_medicines    → membermedicine API (30m 캐시, cfcode + md_medi)
```

**원산지 필터 제약**: herbmedicine API 응답에 원산지 필드가 없어 `get_herb_by_maker` + origin 조합 시 필터 불가. 이 경우 `_type: "notice"` 아이템을 결과 앞에 추가해 LLM3가 사용자에게 안내하도록 처리.

---

## BM25 엔티티 정규화

`scheme_aliases.json`에 등록된 별칭 목록을 BM25로 검색해 표면형을 정규화한다.

- 슬롯 4종: `herb_name`, `maker`, `origin`, `packaging_unit`
- 예: `CK` → `씨케이(주)`, `중국산` → `중국`, `한 근` → `600g`
- 법인 표기 정규화: `씨케이(주)` / `씨케이주식회사` → 핵심 상호 `씨케이` 로 비교 매칭
- False positive 방지: 4자 미만 한국어는 bigram 토큰화 생략 (`중국산` → `국산` 오매칭 방지)
- BM25 threshold: 0.5
