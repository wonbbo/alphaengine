# AlphaEngine systemd 서비스 파일

## 파일 목록

- `alphaengine-bot.service`: Bot 프로세스 (Trading Engine)
- `alphaengine-web.service`: Web 프로세스 (API Server)

## 설치 방법

```bash
# 서비스 파일 복사
sudo cp alphaengine-bot.service /etc/systemd/system/
sudo cp alphaengine-web.service /etc/systemd/system/

# systemd 리로드
sudo systemctl daemon-reload

# 서비스 활성화 (부팅 시 자동 시작)
sudo systemctl enable alphaengine-bot
sudo systemctl enable alphaengine-web
```

## 서비스 관리 명령어

```bash
# 시작
sudo systemctl start alphaengine-bot
sudo systemctl start alphaengine-web

# 중지
sudo systemctl stop alphaengine-bot
sudo systemctl stop alphaengine-web

# 재시작
sudo systemctl restart alphaengine-bot
sudo systemctl restart alphaengine-web

# 상태 확인
sudo systemctl status alphaengine-bot
sudo systemctl status alphaengine-web

# 로그 확인
journalctl -u alphaengine-bot -f
journalctl -u alphaengine-web -f

# 최근 100줄 로그
journalctl -u alphaengine-bot -n 100 --no-pager
```

## 의존성

- Bot 서비스가 먼저 시작되어야 Web 서비스가 시작됨
- 둘 다 network.target 이후에 시작됨

## 사용자 및 권한

서비스 실행 전 alphaengine 사용자와 필요한 디렉토리를 생성해야 합니다.

```bash
# 사용자 생성
sudo useradd -r -s /bin/false alphaengine

# 디렉토리 권한 설정
sudo chown -R alphaengine:alphaengine /opt/alphaengine
```

## 트러블슈팅

```bash
# 서비스 실패 원인 확인
sudo systemctl status alphaengine-bot -l
journalctl -xeu alphaengine-bot

# 권한 문제 확인
ls -la /opt/alphaengine/

# 설정 파일 존재 확인
cat /opt/alphaengine/config/secrets.yaml
```
