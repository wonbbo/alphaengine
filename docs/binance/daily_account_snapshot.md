# Binance Daily Account Snapshot API

## 개요

Binance의 Daily Account Snapshot API는 **일별 계좌 스냅샷**을 조회하는 API입니다.
과거 특정 시점의 자산 상태를 확인할 수 있어, Bot 최초 실행 시 **초기 자산 기록**에 활용합니다.

## API 정보

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /sapi/v1/accountSnapshot` |
| **도메인** | `https://api.binance.com` (SPOT API) |
| **Weight** | 2400 (IP) - **매우 높음** |
| **인증** | USER_DATA (HMAC SHA256 서명 필요) |

> **주의**: Weight가 2400으로 매우 높습니다. 초기화 시 1회만 호출하고, 주기적 호출은 피해야 합니다.

## 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| type | STRING | **YES** | 계좌 유형: `"SPOT"`, `"MARGIN"`, `"FUTURES"` |
| startTime | LONG | NO | 조회 시작 시간 (Unix timestamp, ms) |
| endTime | LONG | NO | 조회 종료 시간 (Unix timestamp, ms) |
| limit | INT | NO | 조회 개수 (최소 7, **최대 30**, 기본값 7) |
| timestamp | LONG | **YES** | 요청 타임스탬프 (ms) |
| recvWindow | LONG | NO | 요청 유효 시간 (ms) |

## 제약사항

- `startTime`/`endTime` 미지정 시: **최근 7일** 반환
- **최대 1개월(30일) 전**까지만 조회 가능
- 조회 기간은 **30일 이하**여야 함
- 일별 스냅샷이므로 **시간 단위 조회 불가** (일 단위)

## 스냅샷 시점 (중요)

> **Daily Snapshot은 UTC 00:00:00 (자정) 기준입니다.**

```
[시간축 예시]
UTC:    00:00 ──────────────────────────────────── 00:00
        │                                          │
     1월 15일                                   1월 16일
     스냅샷 생성                                스냅샷 생성
        │                                          │
KST:  09:00 ──────────────────────────────────── 09:00
     (1월 15일)                                (1월 16일)
```

### 시점 해석

| 시나리오 | 설명 |
|----------|------|
| 1월 15일 스냅샷 | UTC 1월 15일 00:00:00 시점의 자산 상태 |
| 1월 15일 14:00 UTC에 거래 발생 | 이 거래는 1월 15일 스냅샷에 **미반영**, 1월 16일 스냅샷에 반영 |

### 이전 스냅샷 조회 시 주의

**"특정 거래 직전의 자산 상태"**를 구하려면:

```python
# 거래 시점: 2024-01-15 14:00:00 UTC
trade_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

# 그 날 자정(00:00) 스냅샷이 "직전" 상태
# → 1월 15일 스냅샷 조회 (1월 15일 00:00 UTC 기준)
target_date = trade_time.date()  # 2024-01-15

# 만약 거래가 자정 직후(00:01)에 발생했다면?
# → 전날(1월 14일) 스냅샷이 더 가까운 "직전" 상태
if trade_time.hour == 0 and trade_time.minute < 5:
    target_date = (trade_time - timedelta(days=1)).date()
```

### 스냅샷과 거래 시점 관계

```
[1월 15일 00:00 UTC]  [1월 15일 14:00 UTC]  [1월 16일 00:00 UTC]
       │                      │                      │
    스냅샷 A               거래 발생              스냅샷 B
       │                      │                      │
       └──────────────────────┴──────────────────────┘
       
- 거래 "직전" 자산 상태 = 스냅샷 A (1월 15일)
- 거래 "직후" 자산 상태 = 스냅샷 B (1월 16일)
```

## 응답 형식

### 공통 구조

```json
{
  "code": 200,
  "msg": "",
  "snapshotVos": [
    {
      "type": "spot|margin|futures",
      "updateTime": 1576281599000,
      "data": { ... }
    }
  ]
}
```

- `code`: 200이면 성공, 그 외는 에러 코드
- `msg`: 에러 메시지 (성공 시 빈 문자열)
- `snapshotVos`: 스냅샷 배열 (날짜별)

### SPOT 계좌 응답

```json
{
  "code": 200,
  "msg": "",
  "snapshotVos": [
    {
      "type": "spot",
      "updateTime": 1576281599000,
      "data": {
        "totalAssetOfBtc": "0.09942700",
        "balances": [
          {
            "asset": "BTC",
            "free": "0.09905021",
            "locked": "0.00000000"
          },
          {
            "asset": "USDT",
            "free": "1.89109409",
            "locked": "0.00000000"
          }
        ]
      }
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `totalAssetOfBtc` | 총 자산 (BTC 환산) |
| `balances[].asset` | 자산 심볼 |
| `balances[].free` | 가용 잔고 |
| `balances[].locked` | 동결 잔고 |

### FUTURES 계좌 응답

```json
{
  "code": 200,
  "msg": "",
  "snapshotVos": [
    {
      "type": "futures",
      "updateTime": 1576281599000,
      "data": {
        "assets": [
          {
            "asset": "USDT",
            "marginBalance": "118.99782335",
            "walletBalance": "120.23811389"
          }
        ],
        "position": [
          {
            "symbol": "BTCUSDT",
            "entryPrice": "7130.41000000",
            "markPrice": "7257.66239673",
            "positionAmt": "0.01000000",
            "unRealizedProfit": "1.24029054"
          }
        ]
      }
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `assets[].asset` | 자산 심볼 |
| `assets[].walletBalance` | 지갑 잔고 (실제 USDT) |
| `assets[].marginBalance` | 마진 잔고 (실시간 아님, 참고용) |
| `position[].symbol` | 포지션 심볼 |
| `position[].positionAmt` | 포지션 수량 |
| `position[].unRealizedProfit` | 미실현 손익 (포지션 오픈 시점 기준) |

### MARGIN 계좌 응답

```json
{
  "code": 200,
  "msg": "",
  "snapshotVos": [
    {
      "type": "margin",
      "updateTime": 1576281599000,
      "data": {
        "marginLevel": "2748.02909813",
        "totalAssetOfBtc": "0.00274803",
        "totalLiabilityOfBtc": "0.00000100",
        "totalNetAssetOfBtc": "0.00274750",
        "userAssets": [
          {
            "asset": "XRP",
            "borrowed": "0.00000000",
            "free": "1.00000000",
            "interest": "0.00000000",
            "locked": "0.00000000",
            "netAsset": "1.00000000"
          }
        ]
      }
    }
  ]
}
```

## AlphaEngine 활용 방안

### 사용 목적

Bot 최초 실행 시 **"첫 거래 직전의 자산 상태"**를 정확하게 기록하기 위해 사용합니다.

### 활용 시나리오

```
1. Bot 최초 실행 감지
2. 과거 거래 이력 중 가장 오래된 거래 시점 확인
3. 해당 시점 직전의 Daily Snapshot 조회 (SPOT + FUTURES)
4. 초기 자산으로 기록 (InitialCapitalEstablished 이벤트)
5. 이후 모든 PnL 계산의 기준점으로 사용
```

### 장점

| 장점 | 설명 |
|------|------|
| **정확성** | 역산이 아닌 Binance의 실제 일일 스냅샷 데이터 |
| **신뢰성** | 추정치가 아닌 실제 값 |
| **완전성** | SPOT, MARGIN, FUTURES 모두 지원 |

### 제한사항

| 제한 | 영향 | 대응 |
|------|------|------|
| 30일 제한 | 1개월 이상 전 데이터 조회 불가 | 30일 내 최초 실행 권장 |
| Weight 2400 | Rate limit 위험 | 초기화 시 1회만 호출 |
| 일별 스냅샷 | 시간 단위 조회 불가 | 일 단위 정밀도로 충분 |

## 구현 예시

### REST Client 메서드

```python
# adapters/binance/rest_client.py

async def get_account_snapshot(
    self,
    account_type: str,  # "SPOT", "MARGIN", "FUTURES"
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 7,
) -> dict:
    """Daily Account Snapshot 조회
    
    일별 계좌 스냅샷을 조회합니다.
    과거 특정 날짜의 자산 상태를 확인할 때 사용.
    
    Args:
        account_type: 계좌 유형 ("SPOT", "MARGIN", "FUTURES")
        start_time: 조회 시작 시간 (선택)
        end_time: 조회 종료 시간 (선택)
        limit: 조회 개수 (7-30, 기본 7)
        
    Returns:
        스냅샷 응답 딕셔너리
        
    Note:
        - Weight: 2400 (매우 높음)
        - 최대 30일 전까지만 조회 가능
        - 초기화 시 1회만 호출 권장
    """
    params = {
        "type": account_type,
        "limit": min(max(limit, 7), 30),  # 7-30 범위 보장
    }
    
    if start_time:
        params["startTime"] = int(start_time.timestamp() * 1000)
    if end_time:
        params["endTime"] = int(end_time.timestamp() * 1000)
    
    # SPOT API 도메인 사용 (/sapi/v1/...)
    return await self._spot_request(
        "GET",
        "/sapi/v1/accountSnapshot",
        params=params,
        signed=True,
    )
```

### 초기 자산 조회 예시

```python
async def get_initial_capital_from_snapshot(
    self,
    target_date: datetime,
) -> dict[str, Decimal]:
    """특정 날짜의 초기 자산 조회
    
    Args:
        target_date: 조회 대상 날짜
        
    Returns:
        {
            "SPOT_USDT": Decimal("100.00"),
            "FUTURES_USDT": Decimal("400.00"),
            "TOTAL_USDT": Decimal("500.00"),
            "snapshot_date": "2024-01-15",
        }
    """
    start = target_date - timedelta(days=1)
    end = target_date + timedelta(days=1)
    
    # SPOT 스냅샷 조회
    spot_response = await self.get_account_snapshot(
        account_type="SPOT",
        start_time=start,
        end_time=end,
        limit=7,
    )
    
    # FUTURES 스냅샷 조회
    futures_response = await self.get_account_snapshot(
        account_type="FUTURES",
        start_time=start,
        end_time=end,
        limit=7,
    )
    
    # USDT 잔고 추출
    spot_usdt = Decimal("0")
    for snapshot in spot_response.get("snapshotVos", []):
        for balance in snapshot.get("data", {}).get("balances", []):
            if balance["asset"] == "USDT":
                spot_usdt = Decimal(balance["free"]) + Decimal(balance["locked"])
                break
    
    futures_usdt = Decimal("0")
    for snapshot in futures_response.get("snapshotVos", []):
        for asset in snapshot.get("data", {}).get("assets", []):
            if asset["asset"] == "USDT":
                futures_usdt = Decimal(asset["walletBalance"])
                break
    
    return {
        "SPOT_USDT": spot_usdt,
        "FUTURES_USDT": futures_usdt,
        "TOTAL_USDT": spot_usdt + futures_usdt,
        "snapshot_date": target_date.date().isoformat(),
    }
```

## 참고 자료

- [Binance 공식 문서 - Daily Account Snapshot](https://developers.binance.com/docs/wallet/account/daily-account-snapshoot)
- [Binance Wallet API](https://developers.binance.com/docs/wallet/account)

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2024-02-21 | 최초 작성 |
