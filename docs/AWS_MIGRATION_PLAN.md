# Palantiny AWS 마이그레이션 구현 계획서

## 목표 아키텍처

```
[브라우저]
    │
    ├── 정적 파일 (HTML/JS/CSS) ──► [S3 + CloudFront]
    │
    └── API 요청 ──► [EC2 t4g.medium]
                          │
                ┌─────────┼─────────┐
                │         │         │
           [PostgreSQL] [Redis]  [FastAPI + Workers]
           (EC2 내부)  (EC2 내부)      │
                                  ┌───┴───┐
                             [DynamoDB] [Neo4j Aura]
                             (AWS 관리형) (클라우드)
```

## 전체 단계 요약

| 단계 | 분류 | 작업 | 예상 소요 |
|------|------|------|-----------|
| **Step 1** | 인프라 | IAM 설정 (사용자, 역할, 정책) | 10분 |
| **Step 2** | 인프라 | DynamoDB 테이블 생성 (PK/SK/GSI) | 5분 |
| **Step 3** | 인프라 | Neo4j Aura 인스턴스 생성 + 시딩 | 15분 |
| **Step 4** | 코드 | 백엔드 DynamoDB 교체 | 30분 |
| **Step 5** | 인프라 | EC2 인스턴스 생성 + 초기 설정 | 20분 |
| **Step 6** | 인프라 | EC2 보안 그룹 + IAM Role 연결 | 10분 |
| **Step 7** | 코드 | docker-compose.prod.yml 작성 | 15분 |
| **Step 8** | 코드 | deploy.sh 작성 | 10분 |
| **Step 9** | 인프라 | EC2에 Docker 설치 + 최초 배포 | 20분 |
| **Step 10** | 인프라 | S3 버킷 + CloudFront 생성 | 15분 |
| **Step 11** | 코드 | 프론트엔드 환경변수 + 빌드 + 업로드 | 15분 |
| **Step 12** | 검증 | E2E 통합 테스트 | 20분 |

---

## Step 1: IAM 설정

### 1-1. CLI 작업용 IAM 사용자 생성

로컬 터미널에서 AWS 리소스를 생성·관리할 사용자.

```bash
# IAM 사용자 생성
aws iam create-user --user-name palantiny-deployer

# AdministratorAccess 정책 연결 (초기 구성 목적, 이후 최소권한으로 축소 가능)
aws iam attach-user-policy \
  --user-name palantiny-deployer \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess

# 액세스 키 발급 (출력된 키를 안전하게 보관)
aws iam create-access-key --user-name palantiny-deployer
```

```bash
# 로컬 AWS CLI 프로필 등록
aws configure --profile palantiny
# AWS Access Key ID: (위에서 발급한 키)
# AWS Secret Access Key: (위에서 발급한 시크릿)
# Default region name: ap-northeast-2
# Default output format: json
```

### 1-2. EC2용 IAM Role 생성 (DynamoDB 접근)

EC2 인스턴스에 부착할 Role. 이 Role이 있으면 EC2에서 AWS 키 없이 DynamoDB에 접근 가능.

```bash
# Trust Policy 파일 생성
cat > /tmp/ec2-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

# IAM Role 생성
aws iam create-role \
  --role-name palantiny-ec2-role \
  --assume-role-policy-document file:///tmp/ec2-trust-policy.json \
  --profile palantiny

# DynamoDB 풀 액세스 정책 연결
aws iam attach-role-policy \
  --role-name palantiny-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess \
  --profile palantiny

# EC2 인스턴스 프로파일 생성 (Role을 EC2에 붙이기 위한 래퍼)
aws iam create-instance-profile \
  --instance-profile-name palantiny-ec2-profile \
  --profile palantiny

# Role을 프로파일에 추가
aws iam add-role-to-instance-profile \
  --instance-profile-name palantiny-ec2-profile \
  --role-name palantiny-ec2-role \
  --profile palantiny
```

**확인**: AWS 콘솔 → IAM → Roles → `palantiny-ec2-role` 에 DynamoDBFullAccess가 연결되어 있는지 체크.

---

## Step 2: DynamoDB 테이블 생성

### 테이블 설계

| 속성 | 역할 | 타입 |
|------|------|------|
| `session_id` | Partition Key (기본) | String |
| `created_at` | Sort Key | String (ISO 8601) |
| `user_id` | GSI Partition Key | String |

```bash
# 테이블 생성 (PK: session_id, SK: created_at)
aws dynamodb create-table \
  --table-name palantiny-chat-history \
  --attribute-definitions \
    AttributeName=session_id,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
  --key-schema \
    AttributeName=session_id,KeyType=HASH \
    AttributeName=created_at,KeyType=RANGE \
  --global-secondary-indexes '[
    {
      "IndexName": "user_id-created_at-index",
      "KeySchema": [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "created_at", "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"}
    }
  ]' \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-2 \
  --profile palantiny

# 테이블 생성 완료 대기
aws dynamodb wait table-exists \
  --table-name palantiny-chat-history \
  --region ap-northeast-2 \
  --profile palantiny

echo "DynamoDB 테이블 생성 완료"
```

---

## Step 3: Neo4j Aura 생성 + 시딩

### 3-1. Aura 인스턴스 생성

1. [https://console.neo4j.io](https://console.neo4j.io) 접속 → 회원가입
2. **New Instance** → **AuraDB Free** (또는 Professional) 선택
3. 인스턴스 생성 완료 후 아래 정보 메모:
   - Connection URI: `neo4j+s://xxxxxxxx.databases.neo4j.io`
   - Username: `neo4j`
   - Password: (생성 시 발급, 최초 1회만 표시)

### 3-2. 기존 데이터 시딩

```bash
# 로컬에서 Aura에 Cypher 스크립트 실행
cypher-shell \
  -a neo4j+s://<your-aura-endpoint>.databases.neo4j.io \
  -u neo4j \
  -p <your-aura-password> \
  -f ./init_data.cypher
```

> cypher-shell이 없으면: `brew install neo4j` 또는 Neo4j Desktop에서 실행 가능

---

## Step 4: 백엔드 코드 수정

### 4-1. requirements.txt

`motor` 제거, `aioboto3` 추가.

### 4-2. app/core/config.py

MongoDB 설정 제거, DynamoDB/AWS 설정 추가.

### 4-3. app/repositories/chat_history_repository.py

`DynamoDBChatHistoryRepository` 신규 구현 (aioboto3 기반).

### 4-4. app/chatbot_main.py

- `MongoChatHistoryRepository` → `DynamoDBChatHistoryRepository`
- `ALLOWED_ORIGINS` 환경변수 기반 CORS 설정

### 4-5. app/workers/chat_main.py

- `MongoChatHistoryRepository` → `DynamoDBChatHistoryRepository`

> 코드 수정은 이 단계에서 Claude와 함께 파일별로 진행.

---

## Step 5: EC2 인스턴스 생성

### 5-1. 키페어 생성

```bash
aws ec2 create-key-pair \
  --key-name palantiny-key \
  --query 'KeyMaterial' \
  --output text \
  --region ap-northeast-2 \
  --profile palantiny > ~/.ssh/palantiny-key.pem

chmod 400 ~/.ssh/palantiny-key.pem
```

### 5-2. 보안 그룹 생성

```bash
# 보안 그룹 생성
SG_ID=$(aws ec2 create-security-group \
  --group-name palantiny-sg \
  --description "Palantiny EC2 Security Group" \
  --region ap-northeast-2 \
  --profile palantiny \
  --query 'GroupId' --output text)

echo "Security Group ID: $SG_ID"

# SSH (22) - 내 IP만
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp --port 22 \
  --cidr ${MY_IP}/32 \
  --region ap-northeast-2 --profile palantiny

# HTTP (80) - 전체
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp --port 80 \
  --cidr 0.0.0.0/0 \
  --region ap-northeast-2 --profile palantiny

# HTTPS (443) - 전체
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp --port 443 \
  --cidr 0.0.0.0/0 \
  --region ap-northeast-2 --profile palantiny

# FastAPI (8000) - 전체 (CloudFront/ALB 연동 전 임시)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp --port 8000 \
  --cidr 0.0.0.0/0 \
  --region ap-northeast-2 --profile palantiny
```

### 5-3. EC2 인스턴스 생성 (t4g.medium / ARM)

```bash
# Ubuntu 22.04 LTS ARM64 AMI (ap-northeast-2)
AMI_ID="ami-0c9c942bd7bf113a2"  # 실행 전 최신 AMI ID 확인 필요

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type t4g.medium \
  --key-name palantiny-key \
  --security-group-ids $SG_ID \
  --iam-instance-profile Name=palantiny-ec2-profile \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
  --region ap-northeast-2 \
  --profile palantiny \
  --query 'Instances[0].InstanceId' --output text)

echo "Instance ID: $INSTANCE_ID"

# 인스턴스 실행 대기
aws ec2 wait instance-running \
  --instance-ids $INSTANCE_ID \
  --region ap-northeast-2 --profile palantiny

# 퍼블릭 IP 확인
aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text \
  --region ap-northeast-2 --profile palantiny
```

---

## Step 6: EC2 초기 환경 설정

```bash
# EC2 SSH 접속
ssh -i ~/.ssh/palantiny-key.pem ubuntu@<EC2_PUBLIC_IP>

# Docker + Docker Compose 설치
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Git 설치
sudo apt-get update && sudo apt-get install -y git

# 레포지토리 클론
git clone https://github.com/<your-org>/palantiny.git
cd palantiny

# .env.prod 파일 생성 (EC2 내부에서 직접 작성)
cp .env .env.prod
nano .env.prod
# → DATABASE_URL, REDIS_URL, NEO4J_URI (Aura), OPENAI_API_KEY 등 수정
# → MONGODB_URI 삭제, DYNAMODB_TABLE_CHAT 추가
# → AWS_REGION_NAME=ap-northeast-2 (IAM Role 사용 시 키 불필요)
```

---

## Step 7: docker-compose.prod.yml 작성

기존 `docker-compose.yml` 대비 변경 사항:
- `mongo` 서비스 제거
- `neo4j`, `neo4j-seeder` 서비스 제거
- `chatbot_app`, `chat_worker` 의존성에서 `mongo`, `neo4j` 제거
- 환경변수를 AWS 리소스 주소로 변경
- 이미지 빌드 시 `platform: linux/arm64` 명시

> 이 단계에서 Claude와 함께 파일 작성.

---

## Step 8: scripts/deploy.sh 작성

```bash
#!/bin/bash
# EC2 내부에서 실행하는 배포 스크립트
set -e

cd ~/palantiny
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker image prune -f
echo "배포 완료: $(date)"
```

---

## Step 9: 최초 배포 실행 및 검증

```bash
# EC2 내부에서
cd ~/palantiny
docker compose -f docker-compose.prod.yml up -d --build

# 헬스체크
curl http://localhost:8000/health
curl http://localhost:8001/health
```

---

## Step 10: S3 + CloudFront 설정

```bash
# S3 버킷 생성 (버킷명은 전역 유일)
aws s3api create-bucket \
  --bucket palantiny-frontend \
  --region ap-northeast-2 \
  --create-bucket-configuration LocationConstraint=ap-northeast-2 \
  --profile palantiny

# 퍼블릭 액세스 차단 해제 (CloudFront OAC 사용 시 불필요하지만 우선 단순하게)
aws s3api put-public-access-block \
  --bucket palantiny-frontend \
  --public-access-block-configuration \
    BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false \
  --profile palantiny

# 정적 웹사이트 호스팅 활성화
aws s3 website s3://palantiny-frontend \
  --index-document index.html \
  --error-document index.html \
  --profile palantiny

# CloudFront 배포 생성은 AWS 콘솔에서 진행 (JSON 설정이 복잡)
# 콘솔 → CloudFront → Create Distribution → Origin: S3 버킷
```

---

## Step 11: 프론트엔드 빌드 + S3 업로드

```bash
# frontEnd/.env.production 생성
echo "VITE_API_BASE_URL=http://<EC2_PUBLIC_IP>:8000" > frontEnd/.env.production

# 빌드
cd frontEnd
npm install
npm run build

# S3 업로드
aws s3 sync dist/ s3://palantiny-frontend --delete --profile palantiny

# CloudFront 캐시 무효화
aws cloudfront create-invalidation \
  --distribution-id <CLOUDFRONT_DIST_ID> \
  --paths "/*" \
  --profile palantiny
```

---

## Step 12: E2E 검증 체크리스트

- [ ] CloudFront URL로 프론트엔드 접속
- [ ] `/api/v1/auth/verify` 호출 → `session_id` 발급 확인
- [ ] 채팅 메시지 전송 → SSE 스트리밍 응답 수신 확인
- [ ] AWS 콘솔 → DynamoDB → `palantiny-chat-history` 테이블에 레코드 저장 확인
- [ ] EC2 `docker compose logs -f chatbot_app` 에러 없음 확인

---

## 운영 주의사항

### PostgreSQL 데이터 영속성

EC2 재생성 시 데이터 소실을 막으려면 EBS 볼륨을 별도 마운트해야 합니다.

```bash
# docker-compose.prod.yml volumes 섹션에 명시적 경로 지정
volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/postgres  # EBS 마운트 경로
```

### t4g.medium ARM 빌드

로컬(Mac Intel/x86)에서 이미지를 빌드해 EC2로 보내는 경우 플랫폼 불일치 발생.
EC2 내부에서 직접 `docker compose build` 실행 권장.

### CORS 설정

프론트엔드 도메인 확정 후 `ALLOWED_ORIGINS` 환경변수에 CloudFront 도메인만 허용하도록 변경.
