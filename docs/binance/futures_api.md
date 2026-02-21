# Binance FUTURES API (과거 데이터 복구용)

## 개요

Binance USDT-M Futures 계좌의 과거 데이터를 복구하기 위한 API 모음입니다.
Bot 최초 실행 시 누락된 이벤트를 채우는 데 사용합니다.

---

## 1. Income History (futures_income_history)

손익, 수수료, 펀딩비 등 모든 수익/비용 이력을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /fapi/v1/income` |
| **도메인** | `https://fapi.binance.com` |
| **Weight** | 100 (IP) |
| **인증** | USER_DATA (서명 필요) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| symbol | STRING | NO | 특정 심볼 필터 |
| incomeType | STRING | NO | 수익 유형 필터 (아래 표 참조) |
| startTime | LONG | NO | 조회 시작 시간 (ms) |
| endTime | LONG | NO | 조회 종료 시간 (ms) |
| limit | INT | NO | 조회 개수 (기본 100, **최대 1000**) |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### Income Type

| incomeType | 설명 | AlphaEngine 이벤트 |
|------------|------|-------------------|
| `TRANSFER` | 내부 이체 (SPOT ↔ FUTURES) | `TransferCompleted` |
| `WELCOME_BONUS` | 가입 보너스 | - |
| `REALIZED_PNL` | **실현 손익** | `TradeExecuted` (PnL) |
| `FUNDING_FEE` | **펀딩비** (수령/지불) | `FundingFeeReceived/Paid` |
| `COMMISSION` | **거래 수수료** | `FeeCharged` |
| `INSURANCE_CLEAR` | 청산 보험 정산 | - |
| `REFERRAL_KICKBACK` | 추천인 리베이트 | - |
| `COMMISSION_REBATE` | 수수료 리베이트 | - |

### 조회 동작

- `startTime`/`endTime` 미지정 시: **최근 limit건** 반환
- `startTime`~`endTime` 내 데이터가 `limit` 초과 시: `startTime`부터 `limit`건 반환

### 응답 예시

```json
[
  {
    "symbol": "BTCUSDT",
    "incomeType": "REALIZED_PNL",
    "income": "1.23456789",
    "asset": "USDT",
    "info": "",
    "time": 1570636800000,
    "tranId": 9689322392,
    "tradeId": ""
  },
  {
    "symbol": "BTCUSDT",
    "incomeType": "FUNDING_FEE",
    "income": "-0.01234567",
    "asset": "USDT",
    "info": "",
    "time": 1570665600000,
    "tranId": 9689322393,
    "tradeId": ""
  },
  {
    "symbol": "BTCUSDT",
    "incomeType": "COMMISSION",
    "income": "-0.00123456",
    "asset": "USDT",
    "info": "",
    "time": 1570636800000,
    "tranId": 9689322394,
    "tradeId": "12345"
  }
]
```

### AlphaEngine 활용

**가장 중요한 API** - 모든 손익 관련 이벤트 복구에 사용

| incomeType | 처리 방법 |
|------------|-----------|
| `REALIZED_PNL` | 실현 손익 이벤트 생성, Ledger 기록 |
| `FUNDING_FEE` | 펀딩비 이벤트 생성 (양수: 수령, 음수: 지불) |
| `COMMISSION` | 수수료 이벤트 생성, Ledger 비용 기록 |
| `TRANSFER` | SPOT ↔ FUTURES 이체 이벤트 생성 |

### 페이지네이션 예시

```python
async def fetch_all_income(
    self,
    start_time: datetime,
    end_time: datetime,
    income_type: str | None = None,
) -> list[dict]:
    """모든 Income 이력 조회 (페이지네이션 처리)"""
    all_income = []
    current_start = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    
    while current_start < end_ms:
        params = {
            "startTime": current_start,
            "endTime": end_ms,
            "limit": 1000,
        }
        if income_type:
            params["incomeType"] = income_type
        
        result = await self._request("GET", "/fapi/v1/income", params, signed=True)
        
        if not result:
            break
        
        all_income.extend(result)
        
        # 다음 페이지
        last_time = result[-1]["time"]
        current_start = last_time + 1
        
        # Rate limit 고려
        await asyncio.sleep(0.1)
    
    return all_income
```

---

## 2. Transfer History (transfer_history)

SPOT ↔ FUTURES 간 내부 이체 이력을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /sapi/v1/asset/transfer` |
| **도메인** | `https://api.binance.com` (SPOT API) |
| **Weight** | 1 (IP) |
| **인증** | USER_DATA (서명 필요) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| type | ENUM | **YES** | 이체 유형 (아래 표 참조) |
| startTime | LONG | NO | 조회 시작 시간 (ms) |
| endTime | LONG | NO | 조회 종료 시간 (ms) |
| current | INT | NO | 페이지 번호 (기본 1) |
| size | INT | NO | 페이지 크기 (기본 10, **최대 100**) |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### Transfer Type

| type | 설명 |
|------|------|
| `MAIN_UMFUTURE` | SPOT → USDT-M Futures |
| `UMFUTURE_MAIN` | USDT-M Futures → SPOT |
| `MAIN_CMFUTURE` | SPOT → COIN-M Futures |
| `CMFUTURE_MAIN` | COIN-M Futures → SPOT |
| `MAIN_MARGIN` | SPOT → Margin |
| `MARGIN_MAIN` | Margin → SPOT |

### 제약사항

- `startTime`/`endTime` 미지정 시: **최근 7일** 반환
- **최대 6개월** 전까지 조회 가능
- 페이지당 **최대 100건**

### 응답 예시

```json
{
  "total": 2,
  "rows": [
    {
      "asset": "USDT",
      "amount": "100.00000000",
      "type": "MAIN_UMFUTURE",
      "status": "CONFIRMED",
      "tranId": 11415955596,
      "timestamp": 1544433328000
    },
    {
      "asset": "USDT",
      "amount": "50.00000000",
      "type": "UMFUTURE_MAIN",
      "status": "CONFIRMED",
      "tranId": 11415955597,
      "timestamp": 1544433329000
    }
  ]
}
```

### AlphaEngine 활용

- SPOT ↔ FUTURES 이체 이벤트 복구
- 자산 이동 추적 (초기 자산 계산에 필수)
- `TransferCompleted` 이벤트 생성

---

## 3. All Orders (futures_get_all_orders)

모든 주문 이력(체결, 취소, 만료 포함)을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /fapi/v1/allOrders` |
| **도메인** | `https://fapi.binance.com` |
| **Weight** | 5 (IP) |
| **인증** | USER_DATA (서명 필요) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| symbol | STRING | **YES** | 거래쌍 (**필수**) |
| orderId | LONG | NO | 이 주문 ID 이상부터 조회 |
| startTime | LONG | NO | 조회 시작 시간 (ms) |
| endTime | LONG | NO | 조회 종료 시간 (ms) |
| limit | INT | NO | 조회 개수 (기본 500, **최대 1000**) |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### 제약사항

- **`symbol` 필수**: 모든 심볼 한 번에 조회 불가
- `startTime`/`endTime` 미지정 시: **최근 7일** 반환
- 조회 기간: **최대 7일**

### 주문 보존 규칙

주문이 반환되지 **않는** 경우:
- 주문 생성 후 **90일 초과**
- 주문 상태가 `CANCELED` 또는 `EXPIRED`이고:
  - 체결 내역이 없고
  - 주문 생성 후 **3일 초과**

### 응답 예시

```json
[
  {
    "avgPrice": "0.00000",
    "clientOrderId": "ae-550e8400-e29b-41d4",
    "cumQuote": "0",
    "executedQty": "0",
    "orderId": 283194212,
    "origQty": "11",
    "origType": "LIMIT",
    "price": "0.10000",
    "reduceOnly": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "status": "CANCELED",
    "stopPrice": "0",
    "closePosition": false,
    "symbol": "BTCUSDT",
    "time": 1568818199000,
    "timeInForce": "GTC",
    "type": "LIMIT",
    "updateTime": 1568818199000,
    "workingType": "CONTRACT_PRICE",
    "goodTillDate": 0
  }
]
```

### 주문 상태

| status | 설명 |
|--------|------|
| `NEW` | 신규 주문 |
| `PARTIALLY_FILLED` | 부분 체결 |
| `FILLED` | 완전 체결 |
| `CANCELED` | 취소됨 |
| `REJECTED` | 거부됨 |
| `EXPIRED` | 만료됨 |

### AlphaEngine 활용

- 과거 주문 이벤트 복구
- `OrderCreated`, `OrderFilled`, `OrderCancelled` 이벤트 생성
- Command-Event 연결 복구 (client_order_id 기반)

---

## 추가 유용한 API

### 4. Account Trades (futures_account_trades)

체결 이력만 별도로 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /fapi/v1/userTrades` |
| **Weight** | 5 (IP) |

```python
params = {
    "symbol": "BTCUSDT",  # 필수
    "startTime": start_ms,
    "endTime": end_ms,
    "limit": 1000,
}
```

### 5. Position Risk (futures_position_risk)

현재 포지션 정보를 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /fapi/v2/positionRisk` |
| **Weight** | 5 (IP) |

```python
# 모든 포지션 조회
params = {}

# 특정 심볼만
params = {"symbol": "BTCUSDT"}
```

---

## 요약 표

| API | Endpoint | Weight | 조회 범위 | 용도 |
|-----|----------|--------|-----------|------|
| Income History | `/fapi/v1/income` | 100 | - | **손익/수수료/펀딩비** |
| Transfer History | `/sapi/v1/asset/transfer` | 1 | 6개월 | SPOT ↔ FUTURES 이체 |
| All Orders | `/fapi/v1/allOrders` | 5 | 7일 | 주문 이력 |
| User Trades | `/fapi/v1/userTrades` | 5 | - | 체결 이력 |
| Position Risk | `/fapi/v2/positionRisk` | 5 | - | 현재 포지션 |

---

## 데이터 복구 우선순위

Bot 최초 실행 시 과거 데이터 복구 순서:

```
1. Daily Account Snapshot  (초기 자산 확인)
   └─ SPOT + FUTURES 스냅샷 조회
   
2. Transfer History  (SPOT ↔ FUTURES 이체)
   └─ 6개월 전까지 조회
   
3. Income History  (손익/수수료/펀딩비)
   └─ 필수: REALIZED_PNL, FUNDING_FEE, COMMISSION
   
4. All Orders  (주문 이력)
   └─ 7일 제한 주의
   
5. Deposit/Withdraw History  (외부 입출금)
   └─ 90일 전까지 조회
```

---

## 참고 자료

- [Binance Futures API 공식 문서](https://developers.binance.com/docs/derivatives/usds-margined-futures)
- [Binance Wallet API - Transfer](https://developers.binance.com/docs/wallet/asset)

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2024-02-21 | 최초 작성 |
