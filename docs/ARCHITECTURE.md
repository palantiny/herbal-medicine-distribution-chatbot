# Palantiny — 아키텍처 & 플로우 문서

## 1. 시스템 개요

한약재 유통 B2B2C 챗봇 서버. FastAPI 기반, MQ + Pub/Sub 비동기 아키텍처.

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│  PostgreSQL  │    │    Redis     │    │   MongoDB     │
│  (RDBMS)     │    │  Queue/PubSub│    │  (ChatHistory)│
└──────┬───────┘    └──────┬───────┘    └──────┬────────┘
       │                   │                   │
       └───────────┬───────┴───────────────────┘
                   │
          ┌────────┴────────┐
          │   FastAPI App   │
          │                 │
          │  ┌───────────┐  │
          │  │ SQL Worker │  │   ← BRPOP sql_task_queue
          │  │ Chat Worker│  │   ← BRPOP chat_task_queue
          │  └───────────┘  │
          └─────────────────┘
```

---

## 2. 인프라 구성

| 컴포넌트 | 기술 | 용도 |
|---------|------|------|
| API 서버 | FastAPI + Uvicorn | REST/SSE 엔드포인트 |
| RDBMS | PostgreSQL 15 + asyncpg | User, HerbMaster, Inventory, ChatHistory 테이블 |
| 문서 DB | MongoDB + Motor (async) | 채팅 히스토리 영속화 (Mock: 인메모리) |
| 큐/캐시 | Redis 7 | MQ (LPUSH/BRPOP), Pub/Sub (SSE), 캐시 |
| LLM | OpenAI gpt-4o-mini | 의도분석, Text-to-SQL, 최종 답변 (Mock 모드 지원) |

---

## 3. 디렉토리 구조

```
app/
├── main.py                          # FastAPI 진입점, lifespan (Worker 시작/종료)
├── core/
│   ├── config.py                    # Pydantic Settings (env 기반 설정)
│   ├── database.py                  # SQLAlchemy engine, Redis client, init/close
│   └── security.py                  # 파트너 토큰 검증
├── models/
│   ├── user.py                      # User ORM
│   ├── chat_history.py              # ChatHistory ORM
│   ├── herb_master.py               # HerbMaster ORM
│   └── inventory.py                 # Inventory ORM
├── repositories/
│   └── chat_history_repository.py   # MongoDB / Memory 리포지토리 (Protocol)
├── api/v1/
│   ├── auth.py                      # POST /auth/verify
│   └── chat.py                      # POST /chat/{id}/message, GET /chat/{id}/stream
├── services/
│   ├── chat_service.py              # 핵심: 라우팅 → 팬아웃 → 가드레일 → LLM 스트리밍
│   ├── chat_worker.py               # Chat MQ Consumer (BRPOP → process_message)
│   ├── sql_worker.py                # SQL MQ Consumer (BRPOP → SELECT 실행)
│   ├── llm_router.py                # 의도 분석 (Agentic Routing)
│   ├── graph_service.py             # 한약재 지식 그래프 (Mock 온톨로지)
│   ├── guardrail.py                 # 라우트 결과 사전 검증
│   └── history_manager.py           # 128k context 관리 + 요약
└── utils/
    ├── prompts.py                   # 모든 LLM 프롬프트 템플릿
    └── helpers.py                   # session_id 생성 등 유틸
```

---

## 4. API 엔드포인트

### `POST /api/v1/auth/verify`

파트너 토큰 검증 → session_id 발급.

```
Request:  { "partner_token": "abc123" }
Response: { "session_id": "user01_1710000000", "user_id": "...", "recent_history": [...] }
```

### `POST /api/v1/chat/{session_id}/message`

메시지를 큐에 넣고 **즉시 200 OK** 반환.

```
Request:  { "message": "인삼 효능이랑 재고 알려줘", "user_id": "test_001" }
Response: { "status": "queued", "session_id": "test_001_123" }
```

내부 동작:
1. `user_id` 파싱 (body 또는 session_id에서 추출)
2. MongoDB에 user message 즉시 저장 (메시지 유실 방지)
3. `LPUSH chat_task_queue ← {session_id, user_id, message}`

### `GET /api/v1/chat/{session_id}/stream`

Redis Pub/Sub 구독 → SSE 스트리밍.

```
SSE Events:
  data: {"type":"status","content":"질문 의도 분석 중..."}
  data: {"type":"status","content":"복수 데이터 소스 병렬 조회 중... (GRAPH, DB_SQL)"}
  data: {"type":"status","content":"데이터 검증 중..."}
  data: {"type":"token","content":"안"}
  data: {"type":"token","content":"녕"}
  ...
  data: {"type":"end","content":""}
```

> **클라이언트는 GET /stream을 먼저 연결한 뒤 POST /message를 호출해야 합니다.**
> (Pub/Sub race condition 방지)

---

## 5. 핵심 데이터 플로우

```
Client                    API                      Redis MQ           Worker                  Redis Pub/Sub        SSE
  │                        │                          │                  │                        │                  │
  ├─ GET /stream ──────────┼──────────────────────────┼──────────────────┼────────────────────────┼── SUBSCRIBE ─────┤
  │                        │                          │                  │                        │                  │
  ├─ POST /message ────────┤                          │                  │                        │                  │
  │                        ├─ save user msg (Mongo)   │                  │                        │                  │
  │                        ├─ LPUSH ──────────────────┤                  │                        │                  │
  │  ◄── 200 OK ───────────┤                          │                  │                        │                  │
  │                        │                          ├── BRPOP ─────────┤                        │                  │
  │                        │                          │                  ├─ 1. intent analysis    │                  │
  │                        │                          │                  ├─ 2. fan-out (parallel) │                  │
  │                        │                          │                  ├─ 3. guardrail validate │                  │
  │                        │                          │                  ├─ 4. LLM stream ────────┤── PUBLISH ───────┤
  │  ◄─── SSE tokens ─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │                        │                          │                  ├─ 5. save assistant msg  │                  │
  │                        │                          │                  ├─ 6. PUBLISH "end" ─────┤── forward ───────┤
  │  ◄─── SSE "end" ──────────────────────────────────────────────────────────────────────────────────────────────────┤
```

---

## 6. Worker 처리 파이프라인 (`process_message`)

Chat Worker가 큐에서 작업을 꺼내면 아래 파이프라인이 순차 실행됩니다.

```
┌─────────────────────────────────────────────────────────────┐
│                     process_message()                        │
│                                                              │
│  ① 의도 분석 (llm_router.analyze_intent)                     │
│     └─ routes: ["GRAPH", "DB_SQL"] 등                        │
│                                                              │
│  ② 라우트별 데이터 수집                                        │
│     ├─ GENERAL → 스킵 (직행)                                  │
│     ├─ 단일 라우트 → await _execute_route()                   │
│     └─ 복수 라우트 → asyncio.gather(*tasks)  ← 병렬 fan-out   │
│                                                              │
│  ③ Guardrail 사전 검증 (guardrail.validate_context)           │
│     ├─ 규칙 기반: 빈 결과, SQL 에러 패턴 감지                   │
│     ├─ LLM 기반: 질문-데이터 관련성 검증 (Real 모드)             │
│     └─ 결과: validated_context + warnings + dropped_routes    │
│                                                              │
│  ④ 대화 히스토리 조회 (history_manager)                        │
│     └─ 128k 토큰 초과 시 오래된 대화 LLM 요약                   │
│                                                              │
│  ⑤ 프롬프트 선택                                              │
│     ├─ 단일 라우트 → FINAL_ANSWER_*                           │
│     └─ 복수 라우트 → SYNTHESIZER_*                            │
│                                                              │
│  ⑥ LLM 스트리밍 → 토큰마다 redis.publish()                    │
│                                                              │
│  ⑦ "end" 이벤트 발행                                          │
│                                                              │
│  ⑧ MongoDB에 assistant 응답 저장                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Agentic 라우팅

`llm_router.analyze_intent(message)` → 라우트 배열 반환.

| 라우트 | 설명 | 실행기 |
|--------|------|--------|
| `GRAPH` | 한약재 효능, 원산지, 궁합 등 지식 질문 | `graph_service.search_herb_graph()` |
| `CACHE` | 캐시된 재고/가격 빠른 조회 | Redis GET → fallback: GRAPH |
| `DB_SQL` | 실제 DB 조회 (Text-to-SQL) | `_execute_sql_via_redis()` → SQL Worker |
| `GENERAL` | 인사, 일상 대화 | 데이터 수집 없이 LLM 직행 |

복합 질문 예시:
```
"인삼 효능이랑 재고 알려줘" → ["GRAPH", "DB_SQL"]  (병렬 실행)
```

---

## 8. Redis 큐 구조

### Chat Task Queue

```
Key:      chat_task_queue
Pattern:  LPUSH (Producer: POST /message) → BRPOP (Consumer: chat_worker)
Payload:  {"session_id": "...", "user_id": "...", "message": "..."}
```

### SQL Task Queue

```
Key:      sql_task_queue
Pattern:  LPUSH (Producer: chat_service) → BRPOP (Consumer: sql_worker)
Payload:  {"task_id": "uuid", "sql": "SELECT ...", "result_key": "sql_result:uuid"}
Result:   RPUSH result_key → BLPOP (chat_service 대기, 30초 타임아웃)
```

### Pub/Sub 채널

```
Channel:  chat:stream:{session_id}
Events:   {"type": "status|token|error|end", "content": "..."}
```

---

## 9. Guardrail (사전 검증)

LLM 호출 **전에** 라우트 결과를 검증합니다 (Post-validation 아님).

```
라우트 결과 → 규칙 기반 체크 → (Real 모드) LLM 검증 → 통과된 결과만 LLM에 전달
```

| 모드 | 검증 방법 |
|------|----------|
| Mock | 규칙 기반만: 빈 결과, 에러 패턴 (`error`, `오류`, `실패` 등) |
| Real | 규칙 기반 + LLM (`gpt-4o-mini`로 질문-데이터 관련성 판단) |

검증 실패 시:
- 해당 라우트 결과 제거 (`dropped_routes`)
- 경고 메시지를 SSE `status` 이벤트로 전송
- 모든 라우트 실패 시 "일반 지식으로 답변합니다" 안내

---

## 10. 128k Context 관리

`history_manager.get_context_within_limit()`:

```
최근 50턴 로드 → 토큰 수 계산 (tiktoken cl100k_base)
  ├─ ≤ 120,000 tokens → 그대로 사용
  └─ > 120,000 tokens → 전반부 LLM 요약 + 후반부 원문 유지
```

---

## 11. Mock 모드

API 키 없이 전체 플로우를 테스트할 수 있습니다.

```bash
USE_MOCK_LLM=true MOCK_MONGO=true uvicorn app.main:app --reload
```

| 컴포넌트 | Mock 동작 |
|---------|----------|
| 의도 분석 | 키워드 기반 라우팅 ("효능"→GRAPH, "재고"→DB_SQL 등) |
| Text-to-SQL | `SELECT * FROM inventory LIMIT 5` 고정 반환 |
| LLM 스트리밍 | 고정 메시지를 한 글자씩 스트리밍 (20ms 간격) |
| Graph | 내장 온톨로지 딕셔너리에서 검색 |
| MongoDB | `MemoryChatHistoryRepository` (인메모리 dict) |
| Guardrail | 규칙 기반 검증만 (LLM 호출 없음) |
| 히스토리 요약 | 500자 truncate |

---

## 12. 설정 (`app/core/config.py`)

| 키 | 기본값 | 설명 |
|----|-------|------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL 접속 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 접속 |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB 접속 |
| `OPENAI_API_KEY` | `""` | 빈 값이면 Mock 모드 |
| `USE_MOCK_LLM` | `true` | Mock 모드 강제 |
| `MOCK_MONGO` | `true` | 인메모리 ChatHistory |
| `SQL_TASK_QUEUE` | `sql_task_queue` | SQL 작업 큐 키 |
| `CHAT_TASK_QUEUE` | `chat_task_queue` | Chat 작업 큐 키 |
| `CHAT_STREAM_PREFIX` | `chat:stream:` | Pub/Sub 채널 프리픽스 |
| `CONTEXT_MAX_TOKENS` | `120000` | 히스토리 토큰 상한 |

---

## 13. 검증 방법

```bash
# 서버 실행
USE_MOCK_LLM=true MOCK_MONGO=true uvicorn app.main:app --reload

# 터미널 1: SSE 연결 (먼저)
curl -N http://localhost:8000/api/v1/chat/test_001_123/stream

# 터미널 2: 메시지 전송
curl -X POST http://localhost:8000/api/v1/chat/test_001_123/message \
  -H "Content-Type: application/json" \
  -d '{"message": "인삼 효능이랑 재고 알려줘", "user_id": "test_001"}'

# 터미널 2 즉시 응답:
# {"status":"queued","session_id":"test_001_123"}

# 터미널 1 SSE 이벤트:
# data: {"type":"status","content":"질문 의도 분석 중..."}
# data: {"type":"status","content":"복수 데이터 소스 병렬 조회 중... (GRAPH, DB_SQL)"}
# data: {"type":"status","content":"데이터 검증 중..."}
# data: {"type":"token","content":"안"}
# data: {"type":"token","content":"녕"}
# ...
# data: {"type":"end","content":""}
```

---

## 14. 설계 결정 요약

| 결정 | 이유 |
|------|------|
| Redis MQ (LPUSH/BRPOP) | 이미 Redis 사용 중, 추가 인프라 불필요 |
| Redis Pub/Sub → SSE | 워커-클라이언트 간 실시간 토큰 전달 |
| SSE 먼저 연결 → POST 후전송 | Pub/Sub race condition 방지 |
| Guardrail Pre-validation only | 실시간 토큰 스트리밍 UX 유지 (Post는 지연 유발) |
| POST에서 user message 저장 | 워커 처리 전 입력 영속화 → 메시지 유실 방지 |
| chat_worker.py 별도 파일 | sql_worker.py 패턴 일관성 |
| asyncio.gather fan-out | 복수 라우트 병렬 실행으로 지연 최소화 |
| Mock 모드 전면 지원 | 외부 의존성 없이 개발/테스트 가능 |.