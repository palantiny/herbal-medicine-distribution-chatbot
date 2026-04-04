# Palantiny 패키지 & 로컬 UI 테스트

레포 루트의 `palantiny/`는 PostgreSQL·Neo4j·커버리지(LLM 경고) 유틸을 제공합니다. **채팅 영속화는 MongoDB만** 사용합니다(`app.repositories.chat_history_repository.MongoChatHistoryRepository`).

## Neo4j APOC

서브그래프 유틸(`palantiny.layer2_graph.subgraph`)에서 `apoc.path.subgraphAll`을 쓰려면 Neo4j에 **APOC 플러그인**을 설치해야 합니다. 그래프 조회만 할 때는 기존 `app.services.graph_service` 쿼리로도 동작합니다.

## `chatbot_ui.html` 수동 E2E 체크리스트

1. **인프라**: `docker-compose up -d` 또는 로컬에서 PostgreSQL, Redis, MongoDB, Neo4j 기동.
2. **환경**: 프로젝트 루트에 `.env` 생성 ([.env.example](.env.example) 참고). `OPENAI_API_KEY` 필수.
3. **서버**: 프로젝트 루트에서  
   `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
4. **UI**: 브라우저에서 [chatbot_ui.html](chatbot_ui.html) 열기.
   - 서버 주소: `localhost:8000` (또는 LAN IP).
   - Partner Token: 시드 사용자와 맞는 토큰(예: `partner_demo_token_001`).
5. **연결하기**: 성공 시 `/api/v1/auth/verify`가 `recent_history`를 내려주고, Mongo에 저장된 이전 대화가 복원되는지 확인.
6. **SSE**: 메시지 전송 후 스트리밍이 되고, 재접속 시에도 히스토리가 유지되는지 확인.
7. **`file://` 제한**: 일부 브라우저에서 로컬 파일 → `http://localhost` API 호출이 막히면, 레포 루트에서 정적 서버로 HTML을 띄웁니다.  
   예: `python -m http.server 5500` 후 `http://localhost:5500/chatbot_ui.html`

## 유지보수 스크립트

| 스크립트 | 설명 |
|----------|------|
| [scripts/palantiny_load_postgres.py](scripts/palantiny_load_postgres.py) | 가격 CSV 읽기 검증(행 수); 실제 COPY/to_sql 매핑은 후속. |
| [scripts/palantiny_validate_herb_ids.py](scripts/palantiny_validate_herb_ids.py) | 모노그래프 `herb_id` vs `herb_prices_from_csv.cypher`의 `Herb` 이름 집합 diff. |
| [scripts/palantiny_sync_csv_only_herbs_neo4j.py](scripts/palantiny_sync_csv_only_herbs_neo4j.py) | 가격 Cypher에만 있는 한약재용 Neo4j 스텁 MERGE 파일 생성. |

## CLI (선택)

```bash
python -m palantiny.cli.main validate-herb-ids
```

## 테스트

```bash
pip install -r requirements.txt -r requirements-cli.txt
pytest tests/unit -q
```
