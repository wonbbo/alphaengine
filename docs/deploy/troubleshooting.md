# AlphaEngine 문제 해결 가이드

운영 중 발생할 수 있는 문제와 해결 방법입니다.

## 서비스 시작 실패

### 증상

```bash
$ sudo systemctl start alphaengine-bot
Job for alphaengine-bot.service failed...
```

### 진단

```bash
# 상세 상태 확인
sudo systemctl status alphaengine-bot -l

# 최근 로그 확인
journalctl -xeu alphaengine-bot

# 직접 실행 테스트
sudo -u alphaengine bash
cd /opt/alphaengine
source venv/bin/activate
python -m bot
```

### 원인별 해결

#### 1. Python/venv 문제

```bash
# venv 확인
ls -la /opt/alphaengine/venv/bin/python

# venv 재생성
sudo -u alphaengine bash -c "
cd /opt/alphaengine
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
"
```

#### 2. 권한 문제

```bash
# 디렉토리 권한 확인
ls -la /opt/alphaengine/

# 권한 재설정
sudo chown -R alphaengine:alphaengine /opt/alphaengine
sudo chmod 750 /opt/alphaengine
sudo chmod 700 /opt/alphaengine/config
```

#### 3. secrets.yaml 누락/오류

```bash
# 파일 존재 확인
ls -la /opt/alphaengine/config/secrets.yaml

# YAML 문법 검증
python3 -c "import yaml; yaml.safe_load(open('/opt/alphaengine/config/secrets.yaml'))"
```

#### 4. DB 잠금

```bash
# 잠금 파일 확인
ls -la /opt/alphaengine/data/*.db*

# WAL 파일 정리
sqlite3 /opt/alphaengine/data/alphaengine_test.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

## WebSocket 연결 실패

### 증상

로그에서:
```
WebSocket 연결 실패: Connection refused
```

### 진단

```bash
# 네트워크 연결 테스트
curl -v https://fstream.binance.com/ws

# DNS 확인
nslookup fstream.binance.com

# 방화벽 확인
sudo iptables -L -n
```

### 해결

```bash
# 방화벽 설정 (outbound 443 허용)
sudo ufw allow out 443/tcp

# DNS 설정
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

## API 키 오류

### 증상

```
BinanceApiError: code=-2015, msg=Invalid API-key
```

### 해결

1. **API 키 확인**
   - Binance에서 API 키 활성화 상태 확인
   - Testnet: https://testnet.binancefuture.com
   - Production: https://www.binance.com/en/my/settings/api-management

2. **권한 확인**
   - Futures 거래 권한 활성화
   - IP 화이트리스트 확인

3. **secrets.yaml 재설정**
   ```bash
   sudo -u alphaengine vi /opt/alphaengine/config/secrets.yaml
   sudo systemctl restart alphaengine-bot
   ```

## Rate Limit 초과

### 증상

```
HTTP 429 Too Many Requests
```

### 해결

1. **백오프 확인**
   ```bash
   # 로그에서 Rate Limit 확인
   journalctl -u alphaengine-bot | grep -i "rate"
   ```

2. **대기 후 재시작**
   ```bash
   sudo systemctl stop alphaengine-bot
   sleep 60
   sudo systemctl start alphaengine-bot
   ```

3. **Rate Limit 설정 조정** (필요 시)
   - REST 호출 간격 증가
   - WebSocket 우선 사용

## DB 손상

### 증상

```
sqlite3.DatabaseError: database disk image is malformed
```

### 진단

```bash
# 무결성 체크
sqlite3 /opt/alphaengine/data/alphaengine_test.db "PRAGMA integrity_check;"
```

### 해결

1. **백업에서 복구**
   ```bash
   sudo systemctl stop alphaengine-bot alphaengine-web
   
   # 최신 백업 확인
   ls -lt /opt/alphaengine/backups/
   
   # 복구
   tar -xzf /opt/alphaengine/backups/LATEST.tar.gz
   cp LATEST/alphaengine_test.db /opt/alphaengine/data/
   chown alphaengine:alphaengine /opt/alphaengine/data/alphaengine_test.db
   
   sudo systemctl start alphaengine-bot alphaengine-web
   ```

2. **WAL 복구 시도**
   ```bash
   sqlite3 /opt/alphaengine/data/alphaengine_test.db "PRAGMA wal_checkpoint(TRUNCATE);"
   ```

## 메모리 부족

### 증상

```
MemoryError
```
또는 서비스가 OOM Killer에 의해 종료

### 진단

```bash
# 메모리 사용량
free -h

# OOM 로그
dmesg | grep -i "out of memory"
journalctl -k | grep -i "oom"
```

### 해결

1. **메모리 제한 조정**
   ```ini
   # /etc/systemd/system/alphaengine-bot.service
   [Service]
   MemoryMax=1G
   ```

2. **스왑 추가**
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
   ```

## 연결 끊김 반복

### 증상

로그에서 연속적인 재연결:
```
WebSocket 연결 끊김
WebSocket 재연결 시도...
WebSocket 연결 끊김
...
```

### 원인

- 네트워크 불안정
- 서버 과부하
- Binance 서버 문제

### 해결

1. **네트워크 상태 확인**
   ```bash
   ping fstream.binance.com
   mtr fstream.binance.com
   ```

2. **Binance 상태 확인**
   - https://www.binance.com/en/support/announcement

3. **재연결 간격 조정**
   - 백오프 알고리즘 확인

## Web API 502 오류

### 증상

nginx에서 502 Bad Gateway

### 진단

```bash
# 백엔드 서비스 확인
curl http://127.0.0.1:8000/health

# 서비스 상태
sudo systemctl status alphaengine-web

# nginx 로그
tail -f /var/log/nginx/alphaengine_error.log
```

### 해결

1. **서비스 재시작**
   ```bash
   sudo systemctl restart alphaengine-web
   ```

2. **포트 충돌 확인**
   ```bash
   sudo lsof -i :8000
   ```

## 주문 중복

### 증상

같은 주문이 여러 번 체결됨

### 진단

```bash
# 이벤트 확인
sqlite3 /opt/alphaengine/data/alphaengine_test.db \
    "SELECT dedup_key, COUNT(*) as cnt FROM event_store GROUP BY dedup_key HAVING cnt > 1;"
```

### 해결

- dedup_key 생성 로직 확인
- Command idempotency_key 확인

## 진단 명령어 모음

```bash
# 서비스 상태
sudo systemctl status alphaengine-bot alphaengine-web

# 최근 에러
journalctl -u alphaengine-bot -p err --since "1 hour ago"

# 리소스 사용량
top -b -n 1 | grep -E "alphaengine|python"

# 열린 파일/소켓
lsof -p $(pgrep -f "python.*bot")

# 네트워크 연결
ss -tuln | grep 8000
netstat -an | grep -E "ESTABLISHED.*binance"

# DB 상태
sqlite3 /opt/alphaengine/data/alphaengine_test.db "
SELECT 'event_store' as table_name, COUNT(*) as row_count FROM event_store
UNION ALL
SELECT 'command_store', COUNT(*) FROM command_store;
"
```

## 긴급 연락처

- Binance API 지원: https://www.binance.com/en/support
- 시스템 관리자: admin@your-domain.com

## 관련 문서

- [초기 설정](setup.md)
- [systemd 설정](systemd.md)
- [백업/복구](backup.md)
- [모니터링](monitoring.md)
