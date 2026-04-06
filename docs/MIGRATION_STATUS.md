# Palantiny AWS 마이그레이션 상태 보고서

> 최종 업데이트: 2026-04-01

---

## 현재 인프라 요약

| 구성요소 | 서비스 | 세부 정보 |
|---|---|---|
| 컴퓨팅 | EC2 t4g.medium | ARM64, Ubuntu 22.04, 4GB RAM, IP: 15.164.224.237 |
| 챗봇 서버 | server2 (포트 8000) | FastAPI + LangGraph, chat_worker×3, sql_worker×1 |
| 웹앱 서버 | server1 (포트 8001) | FastAPI 웹앱 |
| 채팅 이력 DB | DynamoDB | 테이블: palantiny-chat-history (ap-northeast-2) |
| 관계형 DB | PostgreSQL | EC2 내 Docker 컨테이너 |
| 캐시/MQ | Redis | EC2 내 Docker 컨테이너 |
| 그래프 DB | Neo4j Aura | neo4j+s://20a2b7bf.databases.neo4j.io |
| 프론트엔드 | S3 + CloudFront | d3b68m4w0ltrwq.cloudfront.net |
| CDN/API 프록시 | CloudFront | 배포 ID: E29AWS9P69FIN7 |

---

## CloudFront Behavior 라우팅 구조

| 우선순위 | Path Pattern | Origin | 목적 |
|---|---|---|---|
| 0 | `/api/v1/herbs*` | EC2:8001 | server1 한약재 API |
| 1 | `/api/*` | EC2:8000 | server2 챗봇 API |
| 2 | Default (`*`) | S3 | React 프론트엔드 SPA |

---

## 완료된 작업 (12단계)

### Step 1 — IAM 권한 설정
- [x] IAM 사용자 `palantiny-deployer` 생성 (AdministratorAccess)
- [x] EC2 Instance Profile `palantiny-ec2-role` 생성 (AmazonDynamoDBFullAccess)
- [x] EC2에 Instance Profile 연결 → 액세스 키 없이 DynamoDB 인증

### Step 2 — DynamoDB 테이블 생성
- [x] 테이블 `palantiny-chat-history` 생성
  - Partition Key: `session_id` (String)
  - Sort Key: `created_at` (String)
- [x] GSI `user_id-created_at-index` 생성 (user_id별 채팅 이력 조회용)

### Step 3 — Neo4j Aura 이전
- [x] Neo4j Aura 인스턴스 생성 (Free tier)
- [x] 로컬 Neo4j 컨테이너 데이터 추출 (APOC export → Python 드라이버)
- [x] Aura에 한약재 지식 그래프 데이터 시딩 완료

### Step 4 — 백엔드 코드 DynamoDB 교체
- [x] `requirements.txt`: `motor` → `aioboto3>=13.0.0`
- [x] `app/core/config.py`: MongoDB 설정 제거, DynamoDB/CORS 설정 추가
- [x] `app/repositories/chat_history_repository.py`: `MongoChatHistoryRepository` → `DynamoDBChatHistoryRepository`
- [x] `app/chatbot_main.py`: aioboto3 Session 주입, CORS origins 환경변수화
- [x] `app/workers/chat_main.py`: DynamoDB Repository 적용

### Step 5 — EC2 인스턴스 생성
- [x] t4g.medium (ARM64 Graviton, 4GB RAM, 20GB EBS) 생성
- [x] 보안 그룹: SSH(22), HTTP(80), 8000, 8001 포트 오픈
- [x] 키페어 `palantiny-key2` 생성 (palantiny-key 분실로 재발급)
- [x] Instance Profile `palantiny-ec2-role` 연결

### Step 6 — EC2 기본 환경 구성
- [x] Docker + Docker Compose 설치
- [x] server1, server2 GitHub 레포 클론
- [x] `.env` 파일 작성 (EC2 내부)

### Step 7 — docker-compose.prod.yml 작성
- [x] **server2**: postgres, redis, chatbot_app(8000), chat_worker×3, sql_worker×1
- [x] **server1**: web_app(8001), server2_default 외부 네트워크 연결
- [x] 서비스 간 네트워크: `server2_default` 공유

### Step 8 — deploy.sh 작성 및 최초 배포
- [x] server2 `deploy.sh` 작성 (git pull → docker compose build → up)
- [x] EC2 내부에서 ARM64 이미지 빌드 (로컬 빌드 X)
- [x] server2 최초 배포 성공

### Step 9 — server1 배포
- [x] server1 EC2에서 빌드 및 배포
- [x] server2_default 네트워크 연결 확인

### Step 10 — S3 버킷 생성 및 설정
- [x] S3 버킷 생성: `palantiny-frontend-650679031107-ap-northeast-2-an`
- [x] 퍼블릭 액세스 차단 (OAC 방식)
- [x] 버킷 정책: CloudFront OAC만 허용

### Step 11 — CloudFront 배포
- [x] Distribution 생성 (배포 ID: E29AWS9P69FIN7)
- [x] OAC (Origin Access Control) 설정 → S3 직접 접근 차단
- [x] EC2 Origin 추가 (챗봇 API 프록시)
- [x] Behavior 라우팅 설정 (herbs*, /api/*, default)
- [x] Origin Response Timeout: 30→180초 (LLM 응답 대기)
- [x] 프론트엔드 환경변수 수정: `VITE_API_BASE_URL` 적용
- [x] React 빌드 → S3 업로드 → CloudFront 캐시 무효화

### Step 12 — E2E 검증
- [x] CloudFront 도메인으로 프론트엔드 접속 확인
- [x] 챗봇 답변 동작 확인
- [x] DynamoDB 채팅 이력 저장 확인

---

## 향후 해야 할 작업

### 긴급 (서비스 안정성)

#### 1. CORS 설정 강화
현재 `ALLOWED_ORIGINS=*`로 모든 도메인 허용 중 → 보안 취약

```
# server2 EC2 .env 수정
ALLOWED_ORIGINS=https://d3b68m4w0ltrwq.cloudfront.net
```

#### 2. favicon.ico 403 오류 해결
S3에 favicon 파일이 없어 CloudFront에서 403 반환

```bash
# 로컬 프론트엔드 빌드 결과물에서 S3로 업로드
aws s3 cp frontEnd/dist/favicon.ico s3://palantiny-frontend-650679031107-ap-northeast-2-an/ \
  --profile palantiny
```

#### 3. PostgreSQL 데이터 영속성 확보
현재 Docker 컨테이너 재시작 시 PostgreSQL 데이터 유실 위험

```yaml
# server2 docker-compose.prod.yml에 볼륨 마운트 추가
services:
  postgres:
    volumes:
      - /home/ubuntu/pgdata:/var/lib/postgresql/data
```

### 중요 (기능 완성)

#### 4. han_medicine 테이블 데이터 채우기
현재 server1 PostgreSQL의 `han_medicine` 테이블이 비어있음
- 한약재 가격/재고 데이터 CSV → DB 임포트 스크립트 작성 필요
- `scripts/herb_prices_to_cypher.py` 참고

#### 5. server1 deploy.sh 작성
server2와 동일한 형태의 배포 자동화 스크립트 필요

```bash
#!/bin/bash
# server1/deploy.sh
set -e
git pull origin main
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
echo "server1 deploy complete"
```

### 선택 (운영 편의성)

#### 6. 도메인 연결 (선택)
- Route 53에서 도메인 구매 후 CloudFront Alternate Domain Name 설정
- ACM (AWS Certificate Manager) SSL 인증서 발급 필요

#### 7. EC2 자동 시작 시 Docker 재구동
EC2 재부팅 시 컨테이너 자동 시작되도록 설정

```bash
# EC2에서 실행
sudo systemctl enable docker
# docker-compose.prod.yml에 restart: unless-stopped 추가
```

#### 8. 로그 모니터링
- CloudWatch Logs로 컨테이너 로그 수집
- EC2 알람 설정 (CPU 80%+ 알림)

#### 9. 배포 파이프라인 자동화
- GitHub Actions로 main 브랜치 푸시 시 EC2 자동 배포
- server1, server2 각각 workflow 파일 작성

#### 10. DynamoDB TTL 설정
채팅 이력 자동 만료 설정으로 비용 절감

```
# DynamoDB 콘솔 → 테이블 → Additional settings → TTL 활성화
# Attribute name: expires_at (epoch timestamp)
```

---

## 레포지토리 구조

| 레포 | URL | EC2 경로 | 포트 |
|---|---|---|---|
| server2 (챗봇) | https://github.com/palantiny/server2 | ~/server2 | 8000 |
| server1 (웹앱+프론트) | https://github.com/palantiny/server1 | ~/server1 | 8001 |

## 접속 정보

| 항목 | 값 |
|---|---|
| EC2 SSH | `ssh -i ~/.ssh/palantiny-key2.pem ubuntu@15.164.224.237` |
| 서비스 URL | https://d3b68m4w0ltrwq.cloudfront.net |
| AWS 프로필 | `palantiny` (IAM: palantiny-deployer) |
