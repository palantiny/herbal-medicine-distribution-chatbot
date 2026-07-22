# Palantiny Server2 — 한약재 유통 챗봇 서버

한약재 B2B 유통 플랫폼의 챗봇 백엔드 서버입니다. FastAPI 기반으로 사용자 질문에 대해 **SSE(Server-Sent Events) 실시간 스트리밍**으로 답변하며, 약재 유통 정보(가격·원산지·재고·배송), 효능 안내(모노그래프), 가격 비교, 장바구니 담기를 지원합니다.

## 핵심 기술 스택

- **Backend**: Python 3.11, FastAPI (async)
- **LLM**: OpenAI GPT (Structured Output 라우팅 + 토큰 스트리밍 답변)
- **지식 데이터**: 한약재 모노그래프 70종 (`monograph/*.txt` → `herb_monographs.json`)
- **인프라(선택적)**: PostgreSQL(사용자/인증), Redis, DynamoDB — 미연결 시에도 챗봇은 OpenAI만으로 동작
- **배포**: GitHub Actions → S3 → AWS CodeDeploy → EC2 (Docker Compose)

---

## 주요 개발 내용

### 1. LLM 챗봇 파이프라인 (`app/services/chatbot_pipeline.py`)

한 번의 요청이 아래 순서로 처리됩니다.

1. **라우팅 (Structured Output)** — 사용자 메시지에서 의도를 구조화 추출합니다.
   - `intent`: 일반 상담(`chat`) / 장바구니 담기(`add_to_cart`)
   - `cart_items`: 담을 약재명·수량
   - `mentioned_herbs`: 효능 조회에 쓸 언급 약재명
2. **장바구니 처리** — 추출된 약재명을 판매 카탈로그의 `herb_id`/가격에 매핑해 `add_to_cart` SSE 이벤트로 프론트에 전달합니다. 판매 목록에 없는 약재는 제외됩니다.
3. **컨텍스트 조립** — 판매 약재 카탈로그(12종: 가격·원산지·제조사·재고·배송) + 언급된 약재의 모노그래프(효능·성미·귀경) + 최근 대화 이력을 프롬프트에 주입합니다.
4. **답변 스트리밍** — 최종 답변을 토큰 단위로 SSE 스트리밍합니다.

### 2. 생각 과정(thinking) 실시간 스트리밍

답변 생성을 기다리는 동안 사용자에게 빈 화면 대신 **"질문을 이해하고 있어요…", "판매 중인 약재를 살펴보고 있어요…"** 같은 생각 과정을 글자 단위(`thinking_token`)로 타이핑하듯 스트리밍합니다. 라우팅이 끝나면 결과에 맞춰 "감초 장바구니에 담을 준비를 하고 있어요" 같은 맥락형 메시지로 전환됩니다.

### 3. 모노그래프 지식 베이스 (`app/services/monograph_service.py`)

- 원전 문헌 텍스트 70종(`monograph/*.txt`)을 정제해 `herb_monographs.json`으로 빌드 (`scripts/build_monographs.py`)
- 서버 기동 시 메모리에 로드하여 약재명 → 효능·성미·귀경 정보를 즉시 조회
- LLM이 답변에서 언급한 약재를 자동 추출해 근거 자료로 프롬프트에 주입

### 4. 무상태(stateless) SSE 채팅 API

- `POST /message`가 큐잉 없이 **SSE 응답을 직접 반환** — 클라이언트가 최근 대화 이력을 body에 함께 전송하므로 백엔드는 무상태로 동작
- 표준 SSE 포맷(`data: {JSON}\n\n`)으로 `thinking_token` → `add_to_cart` → `token` → `end` 순서의 이벤트 스트림 제공
- 답변 품질 가드: 취소선·HTML 태그 출력 금지, 내부 식별자(product_id) 비노출 등 프롬프트 규칙 적용

### 5. 파트너 인증 (`app/api/v1/auth.py`)

- `POST /api/v1/auth/verify` — 파트너 토큰 검증 후 `session_id`·`cfcode` 발급 및 최근 대화 기록 반환

---

## API 스펙

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/auth/verify` | partner_token 검증 → session_id, cfcode, 최근 대화 반환 |
| POST | `/api/v1/chat/{session_id}/message` | 메시지 전송 → **SSE 스트리밍 응답** (body에 `message`, `history[]`) |
| DELETE | `/api/v1/chat/{session_id}/history` | 대화 기록 삭제 (무상태 모드에서는 no-op) |
| GET | `/health` | 헬스 체크 |

### SSE 이벤트 타입

```
data: {"type": "thinking_token", "content": "질"}      ← 생각 과정 글자 단위 타이핑
data: {"type": "add_to_cart", "items": [{"herb_id": "1", "herb_name": "감초", "price": 48000, "quantity": 2}]}
data: {"type": "token", "content": "감초는"}            ← 답변 토큰 스트리밍
data: {"type": "error", "content": "..."}              ← 오류 발생 시
data: {"type": "end", "content": ""}                   ← 스트림 종료
```

### 요청 예시

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/test_session/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "감초 2개 장바구니에 담아줘",
    "history": [
      {"role": "user", "content": "감초 가격 알려줘"},
      {"role": "assistant", "content": "감초는 600g 기준 48,000원입니다."}
    ]
  }'
```

---

## 프로젝트 구조

```
app/
├── chatbot_main.py            # FastAPI 진입점 (CORS, lifespan, 라우터 등록)
├── api/v1/
│   ├── auth.py                # 파트너 토큰 인증 → session_id 발급
│   ├── chat.py                # SSE 채팅 엔드포인트
│   └── cache.py               # Redis 캐시 관리 API
├── core/                      # config(pydantic-settings), DB/Redis 연결, 보안
├── data/
│   ├── dummy_herbs.py         # 판매 약재 카탈로그 12종 (가격·원산지·재고·배송)
│   └── herb_monographs.json   # 약재 모노그래프 70종 (효능·성미·귀경)
├── services/
│   ├── chatbot_pipeline.py    # 챗봇 코어: 라우팅 → 장바구니 → 답변 스트리밍
│   ├── monograph_service.py   # 모노그래프 조회 + 프롬프트 포맷팅
│   └── ...                    # 이전 아키텍처 모듈 (pipeline, worker 등 — 현재 우회)
└── utils/prompts.py           # 라우터/답변 시스템 프롬프트
monograph/                     # 모노그래프 원본 텍스트 70종
scripts/
├── build_monographs.py        # monograph/*.txt → herb_monographs.json 빌드
└── after_install.sh           # CodeDeploy 배포 스크립트
tests/                         # pytest 단위 테스트
```

---

## 실행 방법

### 로컬 실행 (OpenAI 키만 필요)

```bash
# .env 파일 생성
echo "OPENAI_API_KEY=sk-..." > .env

pip install -r requirements.txt
uvicorn app.chatbot_main:app --reload
```

PostgreSQL/Redis/DynamoDB가 없어도 챗봇(chat 라우터)은 정상 동작합니다. 인프라 초기화에 실패하면 경고 로그 후 더미 모드로 계속 진행됩니다.

### Docker Compose

```bash
docker-compose up -d --build
```

PostgreSQL(5432), Redis(6379), FastAPI App(8000) 컨테이너가 기동됩니다.

### 프론트엔드 테스트

`chatbot_ui.html`을 브라우저로 열고 서버 주소(예: `localhost:8000`)를 입력해 바로 테스트할 수 있습니다.

- 예시 질문: "감초 가격 알려줘", "인삼이랑 복령 가격 비교해줘", "숙지황 효능이 뭐야?", "백출 2개 장바구니에 담아줘"

---

## 배포 (CI/CD)

```
git push (main)
  → GitHub Actions: 소스 zip → S3 (palantiny-codedeploy/server2/deploy.zip)
  → AWS CodeDeploy (palantiny-server2) → EC2
  → scripts/after_install.sh: docker compose down → build → up -d
```

---

## 개발 히스토리 (아키텍처 변천)

프로젝트는 아래 순서로 발전해 왔으며, 이전 단계의 모듈은 제거하지 않고 우회하는 형태로 코드베이스에 남아 있습니다.

| 단계 | 아키텍처 | 주요 내용 |
|------|---------|----------|
| 1 | **Redis MQ + 3단계 LangGraph** | Redis Queue(BRPOP) 기반 chat_worker 3대 병렬 처리, Text-to-SQL(sql_worker 격리 실행), Cache Warming + Write-Through 캐시, MongoDB → DynamoDB 채팅 이력 마이그레이션 |
| 2 | **Neo4j 지식 그래프** | 한약재 지식 그래프(Text-to-Cypher), multi-intent 라우팅, 2-hop 그래프 템플릿, herb-card UI 마크업, 단계별 thinking SSE |
| 3 | **DJMEDI API 연동** | Neo4j 파이프라인을 외부 유통 API 기반으로 교체, KNOWLEDGE_FIRST/DB_FIRST 라우팅, 모노그래프 주입, 재고/상품 카드 사후 부착 |
| 4 | **더미데이터 기반 (현재)** | Redis MQ/worker 우회 → POST가 SSE 직접 반환하는 무상태 구조, figma 기준 약재 12종 카탈로그, 장바구니 라우팅, 글자 단위 thinking 스트리밍 |

---

## 테스트

```bash
pytest
```

- 라우팅 분기(`test_pipeline_routing.py`), 카드 부착(`test_pipeline_post_cards.py`), 모노그래프 조회(`test_monograph_service.py`), 약재명 추출(`test_herb_mention_extractor.py`) 등 단위 테스트 포함

## 알려진 한계 (MVP)

- 파트너 토큰 인증은 형식 검증 수준 (파트너사 계정 관리 미구현)
- 챗봇 데이터가 더미 카탈로그 12종 기준 (실 재고/가격 연동은 3단계 DJMEDI 모듈에 구현되어 있으나 현재 우회 중)
- 대화 이력을 클라이언트가 보관하는 무상태 구조 (서버측 영구 저장은 DynamoDB 모듈로 존재하나 선택적)
