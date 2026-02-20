# AlphaEngine systemd 서비스 설정

## 개요

AlphaEngine은 두 개의 독립적인 프로세스로 운영됩니다:

| 서비스 | 역할 | 포트 |
|--------|------|------|
| alphaengine-bot | 자동 매매 엔진 | - |
| alphaengine-web | Web API 서버 | 8000 |

## 서비스 파일 위치

- 원본: `/opt/alphaengine/deploy/systemd/`
- 설치 위치: `/etc/systemd/system/`

## Bot 서비스 (alphaengine-bot.service)

```ini
[Unit]
Description=AlphaEngine Bot - Binance Futures Trading Bot
Documentation=https://github.com/yourusername/alphaengine
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=alphaengine
Group=alphaengine
WorkingDirectory=/opt/alphaengine

Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/alphaengine/venv/bin/python -m bot

Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitInterval=60

StandardOutput=journal
StandardError=journal
SyslogIdentifier=alphaengine-bot

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/alphaengine/data /opt/alphaengine/logs

MemoryMax=512M
CPUQuota=100%

[Install]
WantedBy=multi-user.target
```

### 주요 설정 설명

| 설정 | 설명 |
|------|------|
| `Restart=always` | 비정상 종료 시 항상 재시작 |
| `RestartSec=5` | 5초 후 재시작 |
| `StartLimitBurst=5` | 60초 내 최대 5번 재시작 시도 |
| `MemoryMax=512M` | 메모리 제한 512MB |
| `ProtectSystem=strict` | 시스템 디렉토리 보호 |

## Web 서비스 (alphaengine-web.service)

```ini
[Unit]
Description=AlphaEngine Web - API Server
After=network.target alphaengine-bot.service
Wants=alphaengine-bot.service

[Service]
Type=simple
User=alphaengine
Group=alphaengine
WorkingDirectory=/opt/alphaengine

Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/alphaengine/venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000 --workers 1

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Web 서비스 특이사항

- Bot 서비스 시작 후에 시작됨 (`After=alphaengine-bot.service`)
- uvicorn worker 1개 사용 (SQLite 동시성 제한)
- 127.0.0.1만 바인딩 (nginx 통해 외부 접근)

## 서비스 관리 명령어

### 기본 명령어

```bash
# 서비스 상태 확인
sudo systemctl status alphaengine-bot
sudo systemctl status alphaengine-web

# 서비스 시작
sudo systemctl start alphaengine-bot
sudo systemctl start alphaengine-web

# 서비스 중지
sudo systemctl stop alphaengine-web
sudo systemctl stop alphaengine-bot

# 서비스 재시작
sudo systemctl restart alphaengine-bot
sudo systemctl restart alphaengine-web

# 서비스 다시 로드 (설정 변경 후)
sudo systemctl daemon-reload
```

### 로그 확인

```bash
# 실시간 로그
journalctl -u alphaengine-bot -f
journalctl -u alphaengine-web -f

# 최근 100줄
journalctl -u alphaengine-bot -n 100 --no-pager

# 오늘 로그만
journalctl -u alphaengine-bot --since today

# 특정 시간 범위
journalctl -u alphaengine-bot --since "2024-01-01 00:00:00" --until "2024-01-01 23:59:59"

# 에러만 필터
journalctl -u alphaengine-bot -p err
```

### 부팅 시 자동 시작

```bash
# 활성화
sudo systemctl enable alphaengine-bot
sudo systemctl enable alphaengine-web

# 비활성화
sudo systemctl disable alphaengine-bot
sudo systemctl disable alphaengine-web
```

## 서비스 수정

### 서비스 파일 수정 후

```bash
# 1. 파일 수정
sudo vi /etc/systemd/system/alphaengine-bot.service

# 2. systemd 리로드
sudo systemctl daemon-reload

# 3. 서비스 재시작
sudo systemctl restart alphaengine-bot
```

### 환경 변수 추가

`[Service]` 섹션에 `Environment` 추가:

```ini
[Service]
Environment=PYTHONUNBUFFERED=1
Environment=LOG_LEVEL=DEBUG
Environment=CUSTOM_VAR=value
```

## 트러블슈팅

### 서비스가 시작되지 않는 경우

```bash
# 상세 상태 확인
sudo systemctl status alphaengine-bot -l

# 최근 로그 확인
journalctl -xeu alphaengine-bot

# 권한 문제 확인
sudo ls -la /opt/alphaengine/
sudo -u alphaengine /opt/alphaengine/venv/bin/python -c "print('OK')"
```

### 재시작이 반복되는 경우

```bash
# 재시작 제한 확인
systemctl show alphaengine-bot | grep -E "StartLimit|Restart"

# 재시작 카운터 리셋
sudo systemctl reset-failed alphaengine-bot
```

### venv 문제

```bash
# venv 재생성
sudo -u alphaengine bash -c "
cd /opt/alphaengine
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
"
```

## 보안 고려사항

1. **최소 권한 원칙**: alphaengine 사용자로만 실행
2. **네트워크 격리**: Web은 localhost만 바인딩
3. **파일 시스템 보호**: ProtectSystem=strict 사용
4. **리소스 제한**: MemoryMax, CPUQuota 설정
5. **secrets.yaml**: 600 권한으로 보호

## 관련 문서

- [초기 설정](setup.md)
- [nginx 설정](nginx.md)
- [모니터링](monitoring.md)
