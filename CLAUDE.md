# Server2 — 한약재 챗봇 서버

## 한 줄 요약
한약재 관련 질문에 답변하는 B2B 챗봇 서버. FastAPI + Redis MQ + LangGraph 3단계 파이프라인.

---

## 인프라 구조
```
클라이언트 → EC2 :8000 (FastAPI chatbot_app)
                ├─ PostgreSQL (Docker) — 사용자, 채팅 히스토리
                ├─ Redis (Docker)     — Queue / Pub/Sub / Cache
                ├─ chat_worker x3 (Docker) — 파이프라인 실행
                ├─ sql_worker x1 (Docker)  — DB 락 방지 SQL
                ├─ DynamoDB (AWS)     — 채팅 기록 영구 저장
                └─ Neo4j AuraDB (클라우드) — 한약재 지식 그래프
```

---

## 백엔드 지도 (`app/`)

```
chatbot_main.py          # 진입점. CORS, lifespan, 라우터 등록
core/
  config.py              # pydantic-settings. 모든 환경변수 정의
  database.py            # SQLAlchemy async engine, Redis 초기화
  security.py            # 파트너 토큰 검증
api/v1/
  auth.py                # POST /api/v1/auth/verify → session_id 발급
  chat.py                # POST /{session_id}/message (Redis LPUSH)
                         # GET  /{session_id}/stream  (SSE, Redis Pub/Sub)
                         # DELETE /{session_id}/history
  cache.py               # GET/DELETE /api/v1/cache/* (Redis 캐시 관리)
models/
  user.py                # users 테이블
  chat_history.py        # chat_history 테이블 (PostgreSQL)
repositories/
  chat_history_repository.py  # DynamoDB CRUD (aioboto3)
services/
  pipeline.py            # 3단계 LangGraph 파이프라인 (핵심 로직)
  chat_service.py        # 파이프라인 오케스트레이션
  chat_worker.py         # Redis BRPOP → chat_service 호출
  sql_worker.py          # Redis Queue → SQL SELECT 실행
  graph_service.py       # Neo4j AuraDB Cypher 쿼리
  cache_service.py       # Frequency-Based 동적 캐싱
  history_manager.py     # 128k 토큰 제한 + LLM 요약
workers/
  chat_main.py           # chat_worker 실행 진입점
  sql_main.py            # sql_worker 실행 진입점
utils/
  prompts.py             # 3단계 파이프라인 LLM 프롬프트 (Stage1~3)
```

---

## 메시지 처리 흐름

```
1. POST /api/v1/chat/{session_id}/message
   └─ DynamoDB에 user message 저장
   └─ Redis LPUSH chat_task_queue → 즉시 200 OK 반환

2. chat_worker (Redis BRPOP, 3개 병렬)
   └─ history_manager: DynamoDB에서 최근 히스토리 조회
   └─ pipeline.py 실행:
       Stage1: LLM 라우팅 → DIRECT_ANSWER 또는 CYPHER
         └─ CYPHER: Neo4j AuraDB 조회 → Stage2
       Stage2: LLM 라우팅 → DIRECT_ANSWER 또는 SQL
         └─ SQL: sql_task_queue에 LPUSH → sql_worker 결과 대기
       Stage3: 모든 컨텍스트 종합 → 최종 답변 생성
   └─ Redis Pub/Sub PUBLISH (토큰 스트리밍)

3. GET /api/v1/chat/{session_id}/stream (SSE)
   └─ Redis Pub/Sub SUBSCRIBE → type:end 까지 스트리밍
```

---

## 환경변수 (`.env.prod`)
| 키 | 설명 |
|---|---|
| `DATABASE_URL` | PostgreSQL asyncpg URL |
| `REDIS_URL` | Redis URL |
| `NEO4J_URI` | AuraDB 연결 URI (neo4j+s://...) |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | AuraDB 인증 |
| `OPENAI_API_KEY` | GPT 모델 API 키 |
| `DYNAMODB_TABLE_CHAT` | DynamoDB 테이블명 (기본: palantiny-chat-history) |
| `AWS_REGION_NAME` | ap-northeast-2 |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | 빈 값 → EC2 IAM Role 사용 |
| `ALLOWED_ORIGINS` | CORS |
| `POSTGRES_USER/PASSWORD/DB` | Docker postgres 컨테이너용 |

---

## DB / 저장소 역할 분담
| 저장소 | 용도 |
|---|---|
| **PostgreSQL** | users, chat_history 테이블 (ORM) |
| **DynamoDB** | 채팅 기록 영구 저장 (session_id 기준, aioboto3) |
| **Redis Queue** | chat_task_queue (LPUSH/BRPOP), sql_task_queue |
| **Redis Pub/Sub** | chat:stream:{session_id} (토큰 스트리밍) |
| **Redis Cache** | Frequency-Based 동적 TTL 캐시 |
| **Neo4j AuraDB** | 한약재 지식 그래프 (Cypher 쿼리) |

---

## 배포 구조
```
git push → GitHub Actions
  → zip → S3(palantiny-codedeploy/server2/deploy.zip)
  → CodeDeploy(palantiny-server2) → EC2
  → scripts/after_install.sh:
      docker compose down → docker rm -f → build → up -d
```

**appspec.yml**: 파일을 `/home/ubuntu/server2`에 복사 후 `scripts/after_install.sh` 실행 (ubuntu 권한)

---

## 현재 MVP 한계 / 알고 있는 미완성 사항
- 파트너 토큰 인증이 단순 검증만 구현 (실제 파트너사 계정 관리 미완)
- DynamoDB 로컬 테스트 불가 (AWS 연결 필요, Localstack 미설정)
- Neo4j AuraDB 연결 끊김 시 재연결 로직 없음
- chat_history 테이블이 PostgreSQL과 DynamoDB 양쪽에 중복 저장됨 (정리 필요)
