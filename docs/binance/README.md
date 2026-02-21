# Binance API 문서

## 개요

AlphaEngine에서 사용하는 Binance API 레퍼런스 문서입니다.
특히 **과거 데이터 복구 및 초기 자산 기록**에 필요한 API를 정리합니다.

## 문서 목록

### 초기 자산 기록

| 문서 | 용도 |
|------|------|
| [daily_account_snapshot.md](./daily_account_snapshot.md) | 일별 자산 스냅샷 조회 (**초기 자산 기록 핵심**) |

### SPOT 계좌 API

| 문서 | API | 용도 |
|------|-----|------|
| [spot_api.md](./spot_api.md) | 다수 API | SPOT 과거 데이터 복구 |

포함 API:
- `GET /api/v3/exchangeInfo` - 심볼 정보
- `GET /sapi/v1/capital/deposit/hisrec` - 입금 이력
- `GET /sapi/v1/capital/withdraw/history` - 출금 이력
- `GET /api/v3/myTrades` - 체결 이력
- `GET /sapi/v1/convert/tradeFlow` - Convert 거래 이력
- `GET /sapi/v1/asset/dribblet` - Dust 전환 이력

### FUTURES 계좌 API

| 문서 | API | 용도 |
|------|-----|------|
| [futures_api.md](./futures_api.md) | 다수 API | FUTURES 과거 데이터 복구 |

포함 API:
- `GET /fapi/v1/income` - **손익/수수료/펀딩비** (가장 중요)
- `GET /sapi/v1/asset/transfer` - SPOT ↔ FUTURES 이체
- `GET /fapi/v1/allOrders` - 주문 이력
- `GET /fapi/v1/userTrades` - 체결 이력

## API Rate Limit 참고

| Weight | API | 사용 시점 |
|--------|-----|-----------|
| 2400 | Daily Account Snapshot | 초기화 시 1회만 |
| 18000 | Withdraw History | 초기화 시 1회만 |
| 3000 | Convert Trade History | 초기화 시 |
| 100 | Income History | 과거 데이터 복구 |
| 5-20 | All Orders, User Trades | 주기적 Reconcile |
| 1 | Deposit History, Transfer History, Dust Log | 빈번 사용 가능 |

> **주의**: Weight가 높은 API는 Rate Limit에 주의하여 사용해야 합니다.
> 특히 Withdraw History(18000)는 초기화 시에만 호출하세요.

## 데이터 복구 우선순위

Bot 최초 실행 시 과거 데이터 복구 권장 순서:

```
1. Daily Account Snapshot  (초기 자산 확인)
   ├─ SPOT 스냅샷
   └─ FUTURES 스냅샷
   
2. Transfer History  (SPOT ↔ FUTURES 이체)
   └─ 6개월 전까지 조회 가능
   
3. Income History  (손익/수수료/펀딩비)
   ├─ REALIZED_PNL
   ├─ FUNDING_FEE
   └─ COMMISSION
   
4. All Orders  (주문 이력)
   └─ 7일 제한 주의
   
5. Deposit/Withdraw History  (외부 입출금)
   └─ 90일 전까지 조회
   
6. Convert History, Dust Log  (기타 자산 변동)
```

## 관련 코드

| 파일 | 역할 |
|------|------|
| `adapters/binance/rest_client.py` | REST API 클라이언트 |
| `bot/reconciler/reconciler.py` | 과거 데이터 동기화 |
| `bot/bootstrap.py` | Bot 초기화 및 초기 자산 기록 |

## 구현 계획 문서

| 문서 | 용도 |
|------|------|
| [13.AlphaEngine_v2_Event_Recovery_Plan_KR.md](../plan/13.AlphaEngine_v2_Event_Recovery_Plan_KR.md) | **이벤트 복구 및 완전 추적 구현 계획** |

## 참고 자료

- [Binance API 공식 문서](https://developers.binance.com/docs)
- [Binance Futures API](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info)
- [Binance SPOT API](https://developers.binance.com/docs/binance-spot-api-docs)
- [Binance Wallet API](https://developers.binance.com/docs/wallet)
- [Binance Convert API](https://developers.binance.com/docs/convert)

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2024-02-21 | 최초 작성 - Daily Account Snapshot, SPOT API, FUTURES API |
