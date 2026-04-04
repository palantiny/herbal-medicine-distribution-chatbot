# Palantiny — 아키텍처 & 플로우 문서

FastAPI 및 LangGraph 기반의 한약재 유통 자동화 챗봇 서버입니다. SSE(Server-Sent Events)를 활용한 실시간 스트리밍 응답과 지능적인 Caching 전략, Text-to-SQL 파이프라인을 특징으로 합니다.

## 핵심 기술 스택

- **Backend**: Python 3.11, FastAPI, LangGraph (LLM Pipeline)
- **RDBMS**: PostgreSQL (한약재 마스터, 재고, 가격 데이터: `herb_master`, `inventory`, `herb_price_item` 등)
- **NoSQL**: MongoDB (채팅 히스토리 영구 저장소)
- **In-Memory/MQ**: Redis (Redis Queue, Pub/Sub, Cache-First 전략, Write-Through 캐시)
- **Graph DB**: Neo4j (한약재 지식 그래프)
- **LLM**: OpenAI GPT-4o-mini (Text-to-SQL 및 의도 분석)
- **Frontend**: HTML/JS 바닐라 클라이언트 (`chatbot_ui.html`)

## 시스템 아키텍처 및 주요 기능

### 1. LangGraph 기반 LLM 파이프라인 (`pipeline.py`)
- **Stage 1 (Router)**: 질문의 의도를 분석하여 일반 지식/관계, 단순 인사, 정형 데이터(재고/가격) 등으로 라우팅하고 핵심 엔티티(`herb_name`)를 추출합니다.
- **Stage 2 (SQL Execeution & Fallback)**:
  - **Fallback 파서**: LLM이 약재명 추출에 실패하더라도 사용자 질문에서 캐시에 적재된 약재명 225개를 직접 매칭하여 오동작을 방지합니다.
  - **Cache-First 전략**: 약재명이 매칭되면 Database 조회를 생략하고 즉시 Redis 캐시(초고속)에서 데이터를 반환합니다.
  - **Text-to-SQL**: 캐시가 없는(Miss) 복잡한 질의는 LLM이 SQL을 생성하여 비동기 워커(`sql_worker.py`)를 통해 PostgreSQL을 조회합니다.
  - **Write-Through 캐시**: DB에서 새롭게 조회된 데이터는 즉시 동적 TTL(1시간)과 함께 Redis에 캐싱되어 다음 질의를 가속합니다.
- **Stage 3 (Synthesizer)**: 앞선 과정에서 수집된 DB/Cache 데이터를 바탕으로 최종 자연어 응답을 사용자에게 스트리밍합니다.

### 2. 고도화된 캐싱 전략 (`cache_service.py`)
- **Cache Warming**: 서버 구동 시 즉각적으로 DB의 약재 정보를 Redis 장기 캐시에 적재하여 초기 응답 속도를 극대화합니다.
- **LRU Policy**: 최대 50MB 메모리 제한과 `allkeys-lru` 정책을 사용하여 사용량이 적은 캐시부터 자동 삭제합니다.

### 3. 실시간 UI (`chatbot_ui.html`)
- SSE 기반 단어 단위 스트리밍 응답 지원.
- 챗봇의 "의도 분석 중...", "DB 조회 중...", "캐시 조회 중..." 등의 상태 메시지(Pub/Sub) 실시간 표시.
- **외부 접속 지원**: 로컬 환경뿐 아니라 동일 네트워크의 다른 장기기에서도 서버 IP 입력을 통해 챗봇 UI를 즉각적으로 테스트할 수 있습니다.

---

## 차근차근 실행 가이드

### Step 1: 환경 설정 및 .env 구성
프로젝트 루트에 `.env` 파일을 생성하고 다음을 입력합니다:
```env
OPENAI_API_KEY=sk-your-openai-api-key-here
```

### Step 2: Docker Compose로 전체 인프라 및 서버 기동

---

```bash
docker-compose up -d --build
```
- PostgreSQL(5432), Redis(6379), MongoDB(27017), Neo4j(7687, 7474), FastAPI App(8000) 컨테이너가 배포됩니다.
- 서버 구동 시 **자동으로 Cache Warming**되어 225개 이상의 약재 정보가 Redis에 즉시 적재됩니다.
- `docker-compose logs -f app` 명령어로 Cache HIT/MISS 등 실시간 로직을 확인할 수 있습니다.

### Step 3: 시드 데이터 삽입 (최초 1회 한정)

인증에 필요한 User, 한약재, 재고, 가격 정보를 DB에 넣습니다.

```bash
docker-compose exec app python -m scripts.seed_data
docker-compose exec app python -m scripts.seed_herb_prices
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

### Step 4: 웹 프론트엔드에서 챗봇 테스트

1. 리포지토리의 `chatbot_ui.html` 파일을 크롬 등 웹 브라우저에서 실행합니다. (Mac, Windows, 스마트폰 모두 파일 전송 후 열기 가능)
2. 로그인 화면:
   - **서버 주소**: 서버PC가 켜져있는 아이피 및 포트 (예: `192.168.x.x:8000`)
   - **Partner Token**: `partner_demo_token_001` (기본 시드 계정)
3. "연결하기" 클릭 후 채팅을 시작합니다.
   * 예시 질문: "감초 재고 알려줘", "쌍화탕 재료인 약재들의 가격은?", "어제 대추 재고는 얼마라고 했지?"

---

## API 엔드포인트 주요 스펙

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/auth/verify` | partner_token 검증, session_id 발급 및 몽고DB 채팅 이력 반환 |
| POST | `/api/v1/chat/{session_id}/message` | 사용자의 메시지를 받아 워커 큐에 작업 지시 |
| GET | `/api/v1/chat/{session_id}/stream` | SSE 스트리밍 엔드포인트. Status, Token, Error 등을 클라이언트로 Push |

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
app/
├── api/          # FastAPI 라우터 (인증, 채팅, 캐시 API)
├── core/         # DB, Redis 연결 관리 및 Config
├── models/       # SQLAlchemy 모델 (유저, 약재, 재고, 가격표 등)
├── repositories/ # MongoDB 채팅 이력 저장소 패턴
├── services/     # 비즈니스 로직
│   ├── pipeline.py      # LangGraph 기반 LLM 파이프라인 코어
│   ├── cache_service.py # Redis Cache Warming, Get, Set, Invalidate
│   ├── chat_worker.py   # Redis Queue를 듣고 pipeline을 실행하는 워커
│   └── sql_worker.py    # 격리된 Text-to-SQL 실행 워커
└── utils/        # LLM 프롬프트 템플릿 모음
scripts/          # 각종 Seed 데이터 주입 스크립트
```
