# AlphaEngine Production 전환 체크리스트

Testnet 검증 완료 후 Production 환경으로 전환하기 위한 체크리스트입니다.

## 1. Testnet 검증 완료 조건

- [ ] E2E 테스트 전체 통과
  ```bash
  pytest tests/e2e/ -v
  ```
- [ ] 24시간 무중단 Testnet 운영 성공
  ```bash
  python -m scripts.endurance_test --duration 24h
  ```
- [ ] WebSocket 재연결 + REST 복구 정상
- [ ] 중복 주문 0건
- [ ] 이벤트 누락 0건
- [ ] 메모리 누수 없음

## 2. Production API 키 준비

- [ ] Binance Production API 키 발급
  - https://www.binance.com/en/my/settings/api-management
- [ ] API 권한 설정
  - [x] Enable Futures
  - [ ] IP Whitelist (서버 IP 등록)
  - [ ] API Restrictions 확인
- [ ] API 키 보안 저장
  ```bash
  # secrets.yaml 작성 (본인만 읽기)
  chmod 600 /opt/alphaengine/config/secrets.yaml
  ```

## 3. 설정 변경

### secrets.yaml

```yaml
# 변경 전
mode: testnet

# 변경 후
mode: production

production:
  api_key: "YOUR_PRODUCTION_API_KEY"
  api_secret: "YOUR_PRODUCTION_API_SECRET"
```

### 확인 사항

- [ ] `mode: production` 설정
- [ ] Production API Key/Secret 입력
- [ ] web.secret_key 생성 (32자 이상)

## 4. Production DB 준비

```bash
# 새 Production DB 파일 생성
# Bot 최초 실행 시 자동 생성됨

# 또는 스키마 수동 초기화
python -c "
import asyncio
from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
from pathlib import Path

async def init():
    db_path = Path('/opt/alphaengine/data/alphaengine_prod.db')
    async with SQLiteAdapter(db_path) as adapter:
        await init_schema(adapter)
        print('Production DB 초기화 완료')

asyncio.run(init())
"
```

- [ ] `alphaengine_prod.db` 파일 생성
- [ ] DB 무결성 확인
- [ ] 백업 스크립트 Production DB 포함 확인

## 5. 서비스 재시작

```bash
# 서비스 중지
sudo systemctl stop alphaengine-web
sudo systemctl stop alphaengine-bot

# 설정 확인
cat /opt/alphaengine/config/secrets.yaml | grep mode

# 서비스 시작
sudo systemctl start alphaengine-bot
sudo systemctl start alphaengine-web

# 상태 확인
sudo systemctl status alphaengine-bot alphaengine-web
```

## 6. 초기 검증

### 6.1 연결 확인

```bash
# 로그 확인
journalctl -u alphaengine-bot -f

# 예상 로그:
# - "secrets.yaml 로드 완료 (mode=production)"
# - "REST 연결 성공"
# - "WebSocket 연결 성공"
```

### 6.2 잔고 확인

```bash
curl http://localhost:8000/api/dashboard | python3 -m json.tool
```

- [ ] Production 계좌 잔고 표시
- [ ] 포지션 상태 정상

### 6.3 소액 테스트 주문

```bash
# Web API로 테스트 주문 (선택)
curl -X POST http://localhost:8000/api/commands \
  -H "Content-Type: application/json" \
  -d '{
    "command_type": "PlaceOrder",
    "scope": {
      "symbol": "XRPUSDT"
    },
    "payload": {
      "side": "BUY",
      "order_type": "MARKET",
      "quantity": "1"
    }
  }'
```

- [ ] 소액 주문 정상 체결
- [ ] 이벤트 정상 기록
- [ ] 포지션 청산 완료

## 7. 모니터링 설정

- [ ] 헬스 체크 스크립트 활성화
- [ ] 알림 설정 (Slack/Discord)
- [ ] 로그 로테이션 확인
- [ ] 백업 cron 확인

```bash
# 헬스 체크 테스트
/opt/alphaengine/scripts/health_check.sh

# 백업 테스트
/opt/alphaengine/scripts/backup.sh
```

## 8. 롤백 계획 확인

### 즉시 롤백 방법

```bash
# 1. 서비스 중지
sudo systemctl stop alphaengine-bot alphaengine-web

# 2. 모드 변경
sudo -u alphaengine vi /opt/alphaengine/config/secrets.yaml
# mode: production -> mode: testnet

# 3. 서비스 재시작
sudo systemctl start alphaengine-bot alphaengine-web
```

### Production 데이터 보존

```bash
# Production DB 백업 후 Testnet 전환
cp /opt/alphaengine/data/alphaengine_prod.db \
   /opt/alphaengine/backups/alphaengine_prod_$(date +%Y%m%d).db
```

## 9. 문서화

- [ ] 전환 일시 기록
- [ ] 초기 잔고 스냅샷
- [ ] 설정 값 백업

## 10. 최종 확인

| 항목 | 확인 |
|------|------|
| mode: production | [ ] |
| Production API 키 등록 | [ ] |
| Production DB 생성 | [ ] |
| 서비스 정상 실행 | [ ] |
| WebSocket 연결 | [ ] |
| REST API 정상 | [ ] |
| 잔고 조회 성공 | [ ] |
| 소액 테스트 완료 | [ ] |
| 모니터링 활성화 | [ ] |
| 백업 동작 확인 | [ ] |
| 롤백 계획 숙지 | [ ] |

---

## 긴급 연락처

- 시스템 관리자: admin@your-domain.com
- Binance 지원: https://www.binance.com/en/support

## 변경 이력

| 날짜 | 내용 | 담당자 |
|------|------|--------|
| YYYY-MM-DD | Production 전환 | - |

---

**주의**: Production 환경에서는 실제 자금이 사용됩니다. 모든 체크리스트 항목을 확인한 후 전환하세요.
