# AlphaEngine 서버 초기 설정

Ubuntu 22.04 LTS 기준으로 작성되었습니다.

## 1. 시스템 업데이트

```bash
sudo apt update && sudo apt upgrade -y
```

## 2. 필수 패키지 설치

```bash
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    git \
    sqlite3 \
    curl \
    htop
```

## 3. 전용 사용자 생성

```bash
# alphaengine 사용자 생성 (로그인 불가)
sudo useradd -r -m -d /opt/alphaengine -s /bin/false alphaengine

# 사용자 확인
id alphaengine
```

## 4. 디렉토리 구조 생성

```bash
# 메인 디렉토리 구조
sudo mkdir -p /opt/alphaengine/{config,data,logs}

# 권한 설정
sudo chown -R alphaengine:alphaengine /opt/alphaengine
sudo chmod 750 /opt/alphaengine
sudo chmod 700 /opt/alphaengine/config
```

## 5. 코드 배포

### 방법 1: Git Clone (권장)

```bash
# alphaengine 사용자로 전환
sudo -u alphaengine bash

# Git clone
cd /opt/alphaengine
git clone https://github.com/yourusername/alphaengine.git app
cd app
```

### 방법 2: 파일 복사

```bash
# 로컬에서 압축
tar -czf alphaengine.tar.gz \
    --exclude='.venv' \
    --exclude='*.db' \
    --exclude='__pycache__' \
    alphaengine/

# 서버로 전송
scp alphaengine.tar.gz user@server:/tmp/

# 서버에서 압축 해제
sudo -u alphaengine bash -c "cd /opt/alphaengine && tar -xzf /tmp/alphaengine.tar.gz --strip-components=1"
```

## 6. Python 가상환경 설정

```bash
# alphaengine 사용자로 전환
sudo -u alphaengine bash

cd /opt/alphaengine

# venv 생성
python3.11 -m venv venv

# 활성화
source venv/bin/activate

# 의존성 설치
pip install --upgrade pip
pip install -r requirements.txt

# 설치 확인
pip list | grep -E "fastapi|uvicorn|aiosqlite"
```

## 7. 설정 파일 생성

```bash
# secrets.yaml 생성
sudo -u alphaengine bash -c "cat > /opt/alphaengine/config/secrets.yaml << 'EOF'
mode: testnet

production:
  api_key: "YOUR_PRODUCTION_API_KEY"
  api_secret: "YOUR_PRODUCTION_API_SECRET"

testnet:
  api_key: "YOUR_TESTNET_API_KEY"
  api_secret: "YOUR_TESTNET_API_SECRET"

web:
  secret_key: "$(openssl rand -hex 32)"
EOF"

# 권한 설정 (본인만 읽기)
sudo chmod 600 /opt/alphaengine/config/secrets.yaml
```

## 8. 데이터베이스 초기화

```bash
sudo -u alphaengine bash

cd /opt/alphaengine
source venv/bin/activate

# DB 초기화 스크립트 실행 (있는 경우)
python -m core.storage.init_db

# 또는 Bot 한 번 실행하여 스키마 생성
timeout 5 python -m bot || true
```

## 9. systemd 서비스 설치

```bash
# 서비스 파일 복사
sudo cp /opt/alphaengine/deploy/systemd/alphaengine-bot.service /etc/systemd/system/
sudo cp /opt/alphaengine/deploy/systemd/alphaengine-web.service /etc/systemd/system/

# systemd 리로드
sudo systemctl daemon-reload

# 서비스 활성화
sudo systemctl enable alphaengine-bot
sudo systemctl enable alphaengine-web
```

## 10. 서비스 시작

```bash
# Bot 시작
sudo systemctl start alphaengine-bot

# 상태 확인
sudo systemctl status alphaengine-bot

# Web 시작
sudo systemctl start alphaengine-web

# 상태 확인
sudo systemctl status alphaengine-web
```

## 11. 동작 확인

```bash
# 로그 확인
journalctl -u alphaengine-bot -f &
journalctl -u alphaengine-web -f &

# API 테스트
curl http://localhost:8000/health

# DB 파일 확인
ls -la /opt/alphaengine/data/
```

## 체크리스트

- [ ] 시스템 업데이트 완료
- [ ] Python 3.11 설치
- [ ] alphaengine 사용자 생성
- [ ] 디렉토리 구조 생성
- [ ] 코드 배포
- [ ] venv 생성 및 의존성 설치
- [ ] secrets.yaml 설정
- [ ] systemd 서비스 설치
- [ ] 서비스 시작 및 확인

## 다음 단계

1. [nginx 설정](nginx.md) - HTTPS 및 리버스 프록시
2. [모니터링 설정](monitoring.md) - 로그 및 알림
3. [백업 설정](backup.md) - 자동 백업 구성
