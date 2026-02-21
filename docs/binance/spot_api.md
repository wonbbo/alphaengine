# Binance SPOT API (과거 데이터 복구용)

## 개요

Binance SPOT 계좌의 과거 데이터를 복구하기 위한 API 모음입니다.
Bot 최초 실행 시 누락된 이벤트를 채우는 데 사용합니다.

---

## 1. Exchange Info (get_spot_symbol_info)

심볼 정보 및 거래 규칙을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /api/v3/exchangeInfo` |
| **도메인** | `https://api.binance.com` |
| **Weight** | 20 (IP) |
| **인증** | 불필요 (Public) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| symbol | STRING | NO | 특정 심볼 조회 (예: `BNBBTC`) |
| symbols | ARRAY | NO | 여러 심볼 조회 (예: `["BTCUSDT","BNBBTC"]`) |
| permissions | ARRAY | NO | 권한 필터 (`SPOT`, `MARGIN`, `LEVERAGED`) |
| symbolStatus | STRING | NO | 상태 필터 (`TRADING`, `HALT`, `BREAK`) |

### 응답 예시

```json
{
  "timezone": "UTC",
  "serverTime": 1565246363776,
  "rateLimits": [...],
  "symbols": [
    {
      "symbol": "BTCUSDT",
      "status": "TRADING",
      "baseAsset": "BTC",
      "quoteAsset": "USDT",
      "baseAssetPrecision": 8,
      "quoteAssetPrecision": 8,
      "filters": [
        {
          "filterType": "PRICE_FILTER",
          "minPrice": "0.01",
          "maxPrice": "1000000.00",
          "tickSize": "0.01"
        },
        {
          "filterType": "LOT_SIZE",
          "minQty": "0.00001",
          "maxQty": "9000.00",
          "stepSize": "0.00001"
        }
      ],
      "permissions": ["SPOT", "MARGIN"]
    }
  ]
}
```

### AlphaEngine 활용

- 거래 가능한 심볼 목록 조회
- 심볼별 정밀도(precision), 최소 수량 등 거래 규칙 확인
- 과거 거래 복구 시 유효한 심볼인지 검증

---

## 2. Deposit History (get_deposit_history)

입금 이력을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /sapi/v1/capital/deposit/hisrec` |
| **도메인** | `https://api.binance.com` |
| **Weight** | 1 (IP) |
| **인증** | USER_DATA (서명 필요) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| coin | STRING | NO | 특정 코인 필터 |
| status | INT | NO | 상태 필터 (아래 표 참조) |
| startTime | LONG | NO | 조회 시작 시간 (ms) |
| endTime | LONG | NO | 조회 종료 시간 (ms) |
| offset | INT | NO | 페이지 오프셋 (기본 0) |
| limit | INT | NO | 조회 개수 (기본 1000, **최대 1000**) |
| txId | STRING | NO | 트랜잭션 ID 필터 |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### 상태 코드

| status | 설명 |
|--------|------|
| 0 | Pending |
| 1 | **Success** (확정 입금) |
| 2 | Rejected |
| 6 | Credited but cannot withdraw |
| 7 | Wrong deposit |
| 8 | Waiting user confirm |

### 제약사항

- 기본 조회 범위: **최근 90일**
- `startTime`~`endTime` 간격: **최대 90일**

### 응답 예시

```json
[
  {
    "id": "769800519366885376",
    "amount": "100.00000000",
    "coin": "USDT",
    "network": "TRX",
    "status": 1,
    "address": "TKxxxxxxx",
    "txId": "abc123...",
    "insertTime": 1566791463000,
    "confirmTimes": "12/12",
    "unlockConfirm": 12
  }
]
```

### AlphaEngine 활용

- 과거 입금 이벤트 복구
- `DepositCompleted` 이벤트 생성
- 초기 자산 계산 시 입금액 반영

---

## 3. Withdraw History (get_withdraw_history)

출금 이력을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /sapi/v1/capital/withdraw/history` |
| **도메인** | `https://api.binance.com` |
| **Weight** | 18000 (UID) - **매우 높음** |
| **Rate Limit** | 10 requests/second |
| **인증** | USER_DATA (서명 필요) |

> **주의**: Weight가 18000으로 매우 높습니다. 초기화 시에만 사용하세요.

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| coin | STRING | NO | 특정 코인 필터 |
| withdrawOrderId | STRING | NO | 클라이언트 출금 ID |
| status | INT | NO | 상태 필터 (아래 표 참조) |
| startTime | LONG | NO | 조회 시작 시간 (ms) |
| endTime | LONG | NO | 조회 종료 시간 (ms) |
| offset | INT | NO | 페이지 오프셋 |
| limit | INT | NO | 조회 개수 (기본 1000, **최대 1000**) |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### 상태 코드

| status | 설명 |
|--------|------|
| 0 | Email Sent |
| 2 | Awaiting Approval |
| 3 | Rejected |
| 4 | Processing |
| 6 | **Completed** (출금 완료) |

### 제약사항

- 기본 조회 범위: **최근 90일**
- `startTime`~`endTime` 간격: **최대 90일**
- `withdrawOrderId`만 지정 시: **최근 7일** 반환

### 응답 예시

```json
[
  {
    "id": "b6ae22b3aa844210a7041aee7589627c",
    "amount": "50.00000000",
    "transactionFee": "1.00000000",
    "coin": "TRX",
    "status": 6,
    "address": "TKxxxxxxx",
    "txId": "abc123...",
    "applyTime": "2019-10-12 11:12:02",
    "network": "TRX",
    "completeTime": "2019-10-12 11:20:00"
  }
]
```

### AlphaEngine 활용

- 과거 출금 이벤트 복구
- `WithdrawCompleted` 이벤트 생성
- 초기 자산 계산 시 출금액 반영

---

## 4. My Trades (get_my_trades)

SPOT 체결 이력을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /api/v3/myTrades` |
| **도메인** | `https://api.binance.com` |
| **Weight** | 20 (IP) |
| **인증** | USER_DATA (서명 필요) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| symbol | STRING | **YES** | 거래쌍 (**필수**) |
| orderId | LONG | NO | 특정 주문의 체결만 조회 |
| startTime | LONG | NO | 조회 시작 시간 (ms) |
| endTime | LONG | NO | 조회 종료 시간 (ms) |
| fromId | LONG | NO | 이 Trade ID 이후부터 조회 |
| limit | INT | NO | 조회 개수 (기본 500, **최대 1000**) |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### 제약사항

- **`symbol` 필수**: 모든 심볼 한 번에 조회 불가
- 심볼별로 개별 호출 필요
- `startTime`/`endTime` 또는 `fromId` 사용

### 응답 예시

```json
[
  {
    "symbol": "BNBBTC",
    "id": 28457,
    "orderId": 100234,
    "orderListId": -1,
    "price": "0.00010000",
    "qty": "12.00000000",
    "quoteQty": "0.00120000",
    "commission": "0.01200000",
    "commissionAsset": "BNB",
    "time": 1499865549590,
    "isBuyer": true,
    "isMaker": false,
    "isBestMatch": true
  }
]
```

### AlphaEngine 활용

- SPOT 거래 이력 복구 (Convert 제외한 일반 거래)
- `TradeExecuted` 이벤트 생성
- PnL 계산에는 직접 사용하지 않음 (Futures 중심)

---

## 5. Convert Trade History (get_convert_trade_history)

Convert(간편 전환) 거래 이력을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /sapi/v1/convert/tradeFlow` |
| **도메인** | `https://api.binance.com` |
| **Weight** | 3000 (UID) - **높음** |
| **인증** | USER_DATA (서명 필요) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| startTime | LONG | **YES** | 조회 시작 시간 (ms) |
| endTime | LONG | **YES** | 조회 종료 시간 (ms) |
| limit | INT | NO | 조회 개수 (기본 100, **최대 1000**) |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### 제약사항

- `startTime`, `endTime` **모두 필수**
- `startTime`~`endTime` 간격: **최대 30일**
- 30일씩 나눠서 호출 필요

### 응답 예시

```json
{
  "list": [
    {
      "quoteId": "f3b91c525b2644c7bc1e1cd31b6e1aa6",
      "orderId": 940708407462087195,
      "orderStatus": "SUCCESS",
      "fromAsset": "USDT",
      "fromAmount": "100.00000000",
      "toAsset": "BNB",
      "toAmount": "0.38500000",
      "ratio": "0.00385000",
      "inverseRatio": "259.74025974",
      "createTime": 1623381330000
    }
  ],
  "startTime": 1623381330000,
  "endTime": 1623470000000,
  "limit": 100,
  "moreData": false
}
```

### AlphaEngine 활용

- Convert 거래 이력 복구 (일반 거래와 별도)
- USDT ↔ BNB 전환 등 추적
- BNB 수수료 충전 이력 확인

---

## 6. Dust Log (get_dust_log)

소액 자산을 BNB로 전환한 이력을 조회합니다.

### API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /sapi/v1/asset/dribblet` |
| **도메인** | `https://api.binance.com` |
| **Weight** | 1 (IP) |
| **인증** | USER_DATA (서명 필요) |

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| accountType | STRING | NO | `SPOT` 또는 `MARGIN` (기본: `SPOT`) |
| startTime | LONG | NO | 조회 시작 시간 (ms) |
| endTime | LONG | NO | 조회 종료 시간 (ms) |
| timestamp | LONG | **YES** | 요청 타임스탬프 |

### 제약사항

- **2020/12/01 이후** 기록만 반환
- **최근 100건**만 반환

### 응답 예시

```json
{
  "total": 8,
  "userAssetDribblets": [
    {
      "operateTime": 1615985535000,
      "totalTransferedAmount": "0.00132256",
      "totalServiceChargeAmount": "0.00002654",
      "transId": 45178372831,
      "userAssetDribbletDetails": [
        {
          "transId": 4359321,
          "serviceChargeAmount": "0.000009",
          "amount": "0.0009",
          "operateTime": 1615985535000,
          "transferedAmount": "0.000441",
          "fromAsset": "ATOM"
        },
        {
          "transId": 4359321,
          "serviceChargeAmount": "0.00001745",
          "amount": "0.0008",
          "operateTime": 1615985535000,
          "transferedAmount": "0.00088156",
          "fromAsset": "XRP"
        }
      ]
    }
  ]
}
```

### AlphaEngine 활용

- 소액 자산 → BNB 전환 이력 추적
- 자산 변동 사유 추적 (미스터리 잔고 변동 해결)
- Dust 전환도 자산 변동 이벤트로 기록

---

## 요약 표

| API | Endpoint | Weight | 조회 범위 | 용도 |
|-----|----------|--------|-----------|------|
| Exchange Info | `/api/v3/exchangeInfo` | 20 | - | 심볼 정보 |
| Deposit History | `/sapi/v1/capital/deposit/hisrec` | 1 | 90일 | 입금 이력 |
| Withdraw History | `/sapi/v1/capital/withdraw/history` | 18000 | 90일 | 출금 이력 |
| My Trades | `/api/v3/myTrades` | 20 | - | 체결 이력 |
| Convert History | `/sapi/v1/convert/tradeFlow` | 3000 | 30일 | Convert 이력 |
| Dust Log | `/sapi/v1/asset/dribblet` | 1 | 100건 | Dust 전환 |

---

## 참고 자료

- [Binance SPOT API 공식 문서](https://developers.binance.com/docs/binance-spot-api-docs)
- [Binance Wallet API](https://developers.binance.com/docs/wallet)
- [Binance Convert API](https://developers.binance.com/docs/convert)

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2024-02-21 | 최초 작성 |
