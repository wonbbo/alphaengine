# AlphaEngine 전략 개발 가이드

이 문서는 AlphaEngine v2에서 신규 전략을 개발하고 적용하는 방법을 설명합니다.

## 목차

1. [전략 구조 개요](#전략-구조-개요)
2. [OHLCV DataFrame](#ohlcv-dataframe)
3. [Indicator 시스템](#indicator-시스템)
4. [리스크 기반 수량 계산](#리스크-기반-수량-계산)
5. [신규 전략 생성](#신규-전략-생성)
6. [전략 등록 및 적용](#전략-등록-및-적용)
7. [전략 파라미터](#전략-파라미터)
8. [전략 컨텍스트](#전략-컨텍스트)
9. [이벤트 기반 콜백](#이벤트-기반-콜백)
10. [Multi-Timeframe 전략](#multi-timeframe-전략)
11. [Command 발행](#command-발행)
12. [테스트](#테스트)
13. [체크리스트](#체크리스트)

---

## 전략 구조 개요

AlphaEngine의 전략은 `Strategy` 추상 클래스를 상속받아 구현합니다.

```
strategies/
├── base.py                    # Strategy 추상 클래스, 타입 정의
├── __init__.py
├── indicators/                # 재사용 가능한 기술적 지표
│   ├── __init__.py           # 공개 API
│   ├── trend.py              # sma, ema, macd
│   ├── volatility.py         # atr, bollinger_bands
│   └── momentum.py           # rsi, stochastic
└── examples/
    ├── sma_cross.py           # SMA 크로스 (교육용 단순 예제)
    ├── atr_risk_strategy.py   # ATR 기반 리스크 관리 전략 (권장)
    └── __init__.py
```

### 핵심 원칙

1. **전략은 거래소 API를 직접 호출하지 않음** - `CommandEmitter`를 통해 Command 발행
2. **OHLCV는 pandas DataFrame으로 제공** - 효율적인 벡터 연산 지원
3. **Indicator는 모듈에서 import** - 재사용 가능하고 테스트된 함수 사용
4. **상태는 `strategy_state`에 저장** - 틱 간 유지되는 상태
5. **매매 수량은 전략 내부에서 동적 계산** - 리스크 기반

### RiskGuard와 전략의 관계

| 역할 | 담당 |
|------|------|
| **매매 수량 결정** | 전략 (2% 룰 등) |
| **손절/익절 가격** | 전략 (ATR 기반 등) |
| **최종 안전장치** | RiskGuard (최대 포지션, 일일 손실 한도) |
| **책임 소재** | 전략이 최종 책임 |

> RiskGuard는 "안전망"입니다. 전략이 실수로 과도한 주문을 발행해도 RiskGuard가 막아주지만, 
> 이를 의존해서는 안 됩니다. **전략이 스스로 리스크를 관리해야 합니다.**

---

## OHLCV DataFrame

### 데이터 구조

AlphaEngine에서 시장 데이터는 **pandas DataFrame** 형식으로 제공됩니다.

```python
#                              open     high      low    close     volume
# time (DatetimeIndex)                                                       
# 2026-02-21 09:00:00+00:00  2.3450   2.3520   2.3400   2.3510   1234567.0
# 2026-02-21 09:05:00+00:00  2.3510   2.3600   2.3480   2.3590   1345678.0
# ...
```

### DataFrame 표준

| 속성 | 설명 |
|------|------|
| **Index** | `DatetimeIndex` (UTC, timezone-aware), name='time' |
| **open** | 시가 (float64) |
| **high** | 고가 (float64) |
| **low** | 저가 (float64) |
| **close** | 종가 (float64) |
| **volume** | 거래량 (float64) |

### 접근 방법

```python
async def on_tick(self, ctx: StrategyTickContext, emit: CommandEmitter) -> None:
    ohlcv = ctx.ohlcv  # 기본 5분봉 OHLCV DataFrame
    
    # 최신 종가
    latest_close = ohlcv["close"].iloc[-1]
    
    # 최근 10개 캔들의 고가 평균
    high_avg = ohlcv["high"].tail(10).mean()
    
    # 시간 인덱스 활용
    latest_time = ohlcv.index[-1]
    
    # 데이터 길이 확인
    if len(ohlcv) < 20:
        return  # 데이터 부족
```

### 다른 Timeframe 조회

```python
# Multi-Timeframe 데이터 조회
ohlcv_15m = await ctx.get_ohlcv("15m", limit=50)
ohlcv_1h = await ctx.get_ohlcv("1h", limit=24)
ohlcv_4h = await ctx.get_ohlcv("4h", limit=30)
```

---

## Indicator 시스템

### 개요

AlphaEngine은 재사용 가능한 **Indicator 모듈**을 제공합니다. 모든 indicator 함수는 통일된 인터페이스를 따릅니다.

```python
def indicator_name(
    ohlcv: pd.DataFrame,
    params: dict[str, Any],
) -> pd.Series | tuple[pd.Series, ...]
```

### 사용법

```python
from strategies.indicators import sma, ema, atr, rsi, macd, bollinger_bands, stochastic

# 단일 리턴 indicator
sma_20 = sma(ctx.ohlcv, {"period": 20})
ema_12 = ema(ctx.ohlcv, {"period": 12})
atr_14 = atr(ctx.ohlcv, {"period": 14})
rsi_14 = rsi(ctx.ohlcv, {"period": 14})

# 복수 리턴 indicator
macd_line, signal, histogram = macd(ctx.ohlcv, {})
upper, middle, lower = bollinger_bands(ctx.ohlcv, {"period": 20})
percent_k, percent_d = stochastic(ctx.ohlcv, {})
```

### 사용 가능한 Indicator

#### Trend Indicators (`strategies/indicators/trend.py`)

| 함수 | 파라미터 | 반환 | 설명 |
|------|----------|------|------|
| `sma` | `period` (필수), `source` (기본 "close") | `pd.Series` | 단순 이동평균 |
| `ema` | `period` (필수), `source` (기본 "close") | `pd.Series` | 지수 이동평균 |
| `macd` | `fast_period` (12), `slow_period` (26), `signal_period` (9) | `tuple[Series, Series, Series]` | MACD 라인, 시그널, 히스토그램 |

#### Volatility Indicators (`strategies/indicators/volatility.py`)

| 함수 | 파라미터 | 반환 | 설명 |
|------|----------|------|------|
| `atr` | `period` (기본 14) | `pd.Series` | Average True Range |
| `bollinger_bands` | `period` (20), `std_dev` (2.0), `source` ("close") | `tuple[Series, Series, Series]` | 상단, 중간, 하단 밴드 |

#### Momentum Indicators (`strategies/indicators/momentum.py`)

| 함수 | 파라미터 | 반환 | 설명 |
|------|----------|------|------|
| `rsi` | `period` (기본 14), `source` ("close") | `pd.Series` | RSI (0-100) |
| `stochastic` | `k_period` (14), `d_period` (3), `smooth_k` (3) | `tuple[Series, Series]` | %K, %D |

### 최신 값 가져오기

```python
from strategies.indicators import sma, atr

sma_series = sma(ctx.ohlcv, {"period": 20})
atr_series = atr(ctx.ohlcv, {"period": 14})

# 최신 값 가져오기
sma_value = sma_series.iloc[-1]
atr_value = atr_series.iloc[-1]

# NaN 체크 (데이터 부족 시 초기 값들은 NaN)
if pd.isna(sma_value) or pd.isna(atr_value):
    return  # 데이터 부족
```

### 커스텀 Indicator 작성

새로운 indicator를 추가하려면 동일한 인터페이스를 따르세요.

```python
# strategies/indicators/my_indicator.py

from typing import Any
import pandas as pd


def my_indicator(ohlcv: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """커스텀 Indicator
    
    Args:
        ohlcv: OHLCV DataFrame
        params: {
            "period": int (필수) - 기간
        }
        
    Returns:
        pd.Series: 계산된 값
    """
    period = params.get("period")
    if period is None:
        raise ValueError("params['period'] is required")
    
    # 계산 로직
    result = ohlcv["close"].rolling(window=int(period)).mean()
    
    return result
```

---

## 리스크 기반 수량 계산

### 왜 고정 수량을 사용하지 않는가?

고정 수량 사용 시 문제:
- 변동성이 큰 구간에서 과도한 손실
- 변동성이 낮은 구간에서 기회 손실
- 자산 증가/감소에 비례하지 않음

**해결책: 리스크 기반 동적 수량 계산**

### 2% 룰 (Risk Per Trade)

**핵심 원칙**: 매 거래에서 총자산의 2%만 리스크에 노출

```python
risk_amount = account_equity * risk_per_trade  # 예: 10000 * 0.02 = 200 USDT
stop_distance = abs(entry_price - stop_loss_price)  # 예: |100 - 98| = 2 USDT
quantity = risk_amount / stop_distance  # 예: 200 / 2 = 100개
```

### ATR 기반 손절 라인

```python
from strategies.indicators import atr

# ATR 계산 (indicator 모듈 사용)
atr_series = atr(ctx.ohlcv, {"period": 14})
atr_value = Decimal(str(atr_series.iloc[-1]))

# 손절 거리 = ATR × multiplier
stop_distance = atr_value * Decimal("2.0")
stop_loss_price = entry_price - stop_distance  # Long의 경우
```

### 실제 수량 계산 예시

**시나리오**: 
- 기준 자산: 10,000 USDT
- 리스크 비율: 2%
- 진입가: 100 USDT
- ATR(14): 1.5 USDT
- ATR Multiplier: 2

**계산**:
```
1. 손절 거리 = ATR × 2 = 1.5 × 2 = 3 USDT
2. 손절가 = 진입가 - 손절거리 = 100 - 3 = 97 USDT
3. 리스크 금액 = 자산 × 2% = 10,000 × 0.02 = 200 USDT
4. 수량 = 리스크 금액 / 손절 거리 = 200 / 3 = 66.67개

→ 66개 매수 (손절 시 약 198 USDT 손실 = 약 2%)
```

### ConfigStore 리스크/리워드 설정

| 설정 키 | 기본값 | 설명 | 접근 방식 |
|---------|--------|------|-----------|
| `risk_per_trade` | "0.02" | 거래당 리스크 비율 (2%) | `ctx.risk_per_trade` |
| `reward_ratio` | "1.5" | R:R = 1:reward_ratio | `ctx.reward_ratio` |
| `partial_tp_ratio` | "0.5" | 부분 익절 비율 (50%) | `ctx.partial_tp_ratio` |
| `equity_reset_trades` | 50 | 자산 재평가 주기 (거래 수) | `ctx.equity_reset_trades` |

---

## 신규 전략 생성

### 전략 템플릿 (Indicator + DataFrame 기반)

```python
# strategies/my_strategy.py

"""
My Custom Strategy

OHLCV DataFrame과 indicator 모듈을 사용하는 전략 템플릿.
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Any

from strategies.base import (
    Strategy,
    StrategyTickContext,
    CommandEmitter,
    TradeEvent,
    OrderEvent,
)
from strategies.indicators import sma, atr

logger = logging.getLogger(__name__)


class MyStrategy(Strategy):
    """리스크 기반 전략 템플릿
    
    핵심 기능:
    1. OHLCV DataFrame 기반 데이터 처리
    2. Indicator 모듈 사용
    3. ATR 기반 손절 라인 계산
    4. 2% 룰로 수량 동적 계산
    """
    
    @property
    def name(self) -> str:
        return "MyStrategy"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Risk-managed strategy with indicator module"
    
    @property
    def default_params(self) -> dict[str, Any]:
        return {
            # SMA 크로스 파라미터
            "fast_sma_period": 5,
            "slow_sma_period": 20,
            
            # ATR 손절 파라미터
            "atr_period": 14,
            "atr_multiplier": "2.0",
            
            # 거래소 제약
            "min_qty": "1",
            "qty_precision": 0,
        }
    
    async def on_init(self, params: dict[str, Any]) -> None:
        """파라미터 초기화"""
        self.fast_sma_period = int(params.get("fast_sma_period", 5))
        self.slow_sma_period = int(params.get("slow_sma_period", 20))
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = Decimal(str(params.get("atr_multiplier", "2.0")))
        self.min_qty = Decimal(str(params.get("min_qty", "1")))
        self.qty_precision = int(params.get("qty_precision", 0))
        
        logger.info(f"{self.name} initialized")
    
    async def on_start(self, ctx: StrategyTickContext) -> None:
        """전략 시작 - 상태 초기화"""
        state = ctx.strategy_state
        usdt = ctx.usdt_balance
        
        state["account_equity"] = usdt.total if usdt else Decimal("0")
        state["trade_count_since_reset"] = 0
        state["total_trade_count"] = 0
        state["prev_fast_above"] = None
        
        logger.info(f"{self.name} started on {ctx.symbol}")
    
    async def on_tick(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """틱 처리"""
        if not ctx.can_trade:
            return
        
        ohlcv = ctx.ohlcv
        state = ctx.strategy_state
        
        # 데이터 충분성 검증
        required_rows = max(self.slow_sma_period, self.atr_period + 1)
        if len(ohlcv) < required_rows:
            return
        
        # SMA 계산 (indicator 모듈 사용)
        fast_sma_series = sma(ohlcv, {"period": self.fast_sma_period})
        slow_sma_series = sma(ohlcv, {"period": self.slow_sma_period})
        
        fast_sma_value = fast_sma_series.iloc[-1]
        slow_sma_value = slow_sma_series.iloc[-1]
        
        # NaN 체크
        if fast_sma_value != fast_sma_value or slow_sma_value != slow_sma_value:
            return
        
        fast_above = fast_sma_value > slow_sma_value
        prev_fast_above = state.get("prev_fast_above")
        state["prev_fast_above"] = fast_above
        
        if prev_fast_above is None:
            return
        
        # 포지션 없을 때만 진입
        if not ctx.has_position:
            if fast_above and not prev_fast_above:
                # 골든 크로스 → Long 진입
                await self._enter_long(ctx, emit, state)
            elif not fast_above and prev_fast_above:
                # 데드 크로스 → Short 진입
                await self._enter_short(ctx, emit, state)
    
    async def _enter_long(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """Long 진입"""
        entry_price = ctx.current_price
        if not entry_price:
            return
        
        # ATR 계산 (indicator 모듈 사용)
        atr_series = atr(ctx.ohlcv, {"period": self.atr_period})
        atr_value = atr_series.iloc[-1]
        
        if atr_value != atr_value:  # NaN 체크
            return
        
        atr_decimal = Decimal(str(atr_value))
        
        # 손절 계산
        stop_distance = atr_decimal * self.atr_multiplier
        stop_loss_price = entry_price - stop_distance
        
        # 2% 룰로 수량 계산
        qty = self._calculate_position_size(
            account_equity=state["account_equity"],
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_per_trade=ctx.risk_per_trade,
        )
        
        if qty < self.min_qty:
            return
        
        # 주문 발행
        await emit.place_order(
            side="BUY",
            order_type="MARKET",
            quantity=str(qty),
        )
        
        await emit.place_order(
            side="SELL",
            order_type="STOP_MARKET",
            quantity=str(qty),
            stop_price=str(stop_loss_price),
            reduce_only=True,
        )
    
    async def _enter_short(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """Short 진입 (Long과 반대)"""
        # ... 구현
        pass
    
    def _calculate_position_size(
        self,
        account_equity: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        risk_per_trade: Decimal | None = None,
    ) -> Decimal:
        """2% 룰 기반 포지션 사이즈 계산"""
        risk_ratio = risk_per_trade or Decimal("0.02")
        risk_amount = account_equity * risk_ratio
        stop_distance = abs(entry_price - stop_loss_price)
        
        if stop_distance == Decimal("0"):
            return Decimal("0")
        
        raw_qty = risk_amount / stop_distance
        
        return raw_qty.quantize(
            Decimal(10) ** -self.qty_precision,
            rounding=ROUND_DOWN,
        )
```

---

## 전략 등록 및 적용

### secrets.yaml 설정

```yaml
strategy:
  module: "strategies.examples.atr_risk_strategy"
  class: "AtrRiskManagedStrategy"
  auto_start: true
  params:
    atr_period: 14
    atr_multiplier: "2.0"
    fast_sma_period: 5
    slow_sma_period: 20
    min_qty: "1"
    qty_precision: 0
```

**주의**: `quantity`는 params에 설정하지 않습니다. 전략 내부에서 리스크 기반으로 동적 계산됩니다.

### 적용 절차

1. 전략 파일 생성: `strategies/my_strategy.py`
2. secrets.yaml 수정: `strategy` 섹션 업데이트
3. 봇 재시작: `python -m bot`

---

## 전략 파라미터

### 권장 파라미터 구조

```python
@property
def default_params(self) -> dict[str, Any]:
    return {
        # === 전략 고유 파라미터 ===
        "fast_sma_period": 5,
        "slow_sma_period": 20,
        
        # === ATR 손절 파라미터 ===
        "atr_period": 14,
        "atr_multiplier": "2.0",
        
        # === 거래소 제약 ===
        "min_qty": "1",
        "qty_precision": 0,
    }
```

**절대 포함하지 않는 것**: `quantity` (전략 내부에서 계산)

---

## 전략 컨텍스트

`StrategyTickContext`는 모든 콜백에서 사용 가능한 정보를 제공합니다.

### 주요 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `ctx.symbol` | `str` | 거래 심볼 |
| `ctx.now` | `datetime` | 현재 시간 (UTC) |
| `ctx.ohlcv` | `pd.DataFrame` | **OHLCV DataFrame** |
| `ctx.bars` | `list[Bar]` | 캔들 데이터 (레거시) |
| `ctx.current_price` | `Decimal \| None` | 현재가 |
| `ctx.position` | `Position \| None` | 현재 포지션 |
| `ctx.has_position` | `bool` | 포지션 보유 여부 |
| `ctx.balances` | `dict[str, Balance]` | 잔고 |
| `ctx.usdt_balance` | `Balance \| None` | USDT 잔고 |
| `ctx.open_orders` | `list[OpenOrder]` | 미체결 주문 |
| `ctx.strategy_state` | `dict` | 틱 간 유지되는 상태 |
| `ctx.can_trade` | `bool` | 거래 가능 여부 |
| `ctx.risk_per_trade` | `Decimal` | 거래당 리스크 비율 |
| `ctx.reward_ratio` | `Decimal` | R:R 비율 |

### OHLCV vs bars

| 속성 | 타입 | 권장 |
|------|------|------|
| `ctx.ohlcv` | `pd.DataFrame` | **권장** - 벡터 연산, indicator 모듈과 호환 |
| `ctx.bars` | `list[Bar]` | 레거시 - 하위 호환용 |

```python
# 권장: DataFrame 사용
ohlcv = ctx.ohlcv
sma_20 = sma(ohlcv, {"period": 20})

# 레거시: list[Bar] (하위 호환)
bars = ctx.bars  # 사용 자제
```

### Multi-Timeframe 조회

```python
# DataFrame으로 조회 (권장)
ohlcv_15m = await ctx.get_ohlcv("15m", limit=50)
ohlcv_1h = await ctx.get_ohlcv("1h", limit=24)

# 레거시 (하위 호환)
bars_15m = await ctx.get_bars("15m", limit=50)
```

---

## 이벤트 기반 콜백

### 콜백 비교

| 구분 | on_tick() | on_trade() / on_order_update() |
|------|-----------|-------------------------------|
| 호출 시점 | 5분 간격 | WebSocket 이벤트 즉시 |
| 지연 | 최대 5분 | 밀리초 |
| 용도 | 진입 판단 | 즉시 반응 (손절 조정) |
| 필수 | **필수** | 선택 |

### TradeEvent

체결 발생 시 `on_trade()` 콜백으로 전달:

```python
@dataclass(frozen=True)
class TradeEvent:
    trade_id: str
    order_id: str
    client_order_id: str | None  # "ae-xxx"면 AlphaEngine 주문
    symbol: str
    side: str              # "BUY" | "SELL"
    price: Decimal
    quantity: Decimal
    realized_pnl: Decimal  # 청산 시 실현 손익
    commission: Decimal
    commission_asset: str
    timestamp: datetime
    
    # 주요 속성
    is_reduce: bool        # 청산 체결 (realized_pnl != 0)
    is_profitable: bool    # 이익 실현
    is_alphaengine_order: bool  # AlphaEngine 주문 여부
```

### 활용 예시

```python
async def on_trade(
    self,
    trade: TradeEvent,
    ctx: StrategyTickContext,
    emit: CommandEmitter,
) -> None:
    """부분 익절 후 Break-Even 손절"""
    state = ctx.strategy_state
    
    if trade.is_reduce and trade.is_profitable:
        if not state.get("partial_tp_done"):
            state["partial_tp_done"] = True
            await self._move_stop_to_breakeven(ctx, emit, state)
```

---

## Multi-Timeframe 전략

### ctx.get_ohlcv() 사용

```python
async def on_tick(self, ctx: StrategyTickContext, emit: CommandEmitter) -> None:
    ohlcv_5m = ctx.ohlcv                              # 기본 5분봉
    ohlcv_15m = await ctx.get_ohlcv("15m", limit=50)
    ohlcv_1h = await ctx.get_ohlcv("1h", limit=24)
    ohlcv_4h = await ctx.get_ohlcv("4h", limit=30)
    
    # 각 timeframe에서 indicator 계산
    from strategies.indicators import sma
    
    sma_5m = sma(ohlcv_5m, {"period": 20})
    sma_1h = sma(ohlcv_1h, {"period": 20})
    
    # 상위 timeframe 추세 확인
    if sma_1h.iloc[-1] > sma_1h.iloc[-2]:  # 1시간봉 상승 추세
        # 5분봉에서 진입 신호 찾기
        pass
```

### 지원 Timeframe

`1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`

---

## Command 발행

### 주문 생성

```python
await emit.place_order(
    side="BUY",              # "BUY" | "SELL"
    order_type="MARKET",     # "MARKET" | "LIMIT" | "STOP_MARKET" 등
    quantity="100",          # 수량 (전략에서 계산된 값)
    price=None,              # LIMIT 주문 시
    stop_price=None,         # STOP 주문 시
    reduce_only=False,       # 청산 전용 여부
)
```

### 포지션 청산

```python
await emit.close_position(reduce_only=True)
```

### 주문 취소

```python
await emit.cancel_order(exchange_order_id="123456")
await emit.cancel_all_orders()
```

---

## 테스트

### Indicator 단위 테스트

```python
# tests/unit/strategies/indicators/test_trend.py

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta

from strategies.indicators.trend import sma, ema


def create_sample_ohlcv(num_rows: int = 50) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성"""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = [base_time + timedelta(minutes=5 * i) for i in range(num_rows)]
    
    df = pd.DataFrame({
        "time": times,
        "open": [100.0 + i for i in range(num_rows)],
        "high": [101.0 + i for i in range(num_rows)],
        "low": [99.0 + i for i in range(num_rows)],
        "close": [100.5 + i for i in range(num_rows)],
        "volume": [1000.0] * num_rows,
    })
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    
    return df


class TestSma:
    def test_sma_basic(self):
        ohlcv = create_sample_ohlcv()
        result = sma(ohlcv, {"period": 5})
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv)
        assert not pd.isna(result.iloc[-1])
    
    def test_sma_period_required(self):
        ohlcv = create_sample_ohlcv()
        
        with pytest.raises(ValueError, match="period"):
            sma(ohlcv, {})
```

### 테스트 실행

```bash
.venv\Scripts\python.exe -m pytest tests/unit/strategies/indicators/ -v
```

---

## 체크리스트

### 필수

- [ ] `Strategy` 클래스 상속
- [ ] `name`, `version`, `default_params` 구현
- [ ] `on_init()`, `on_tick()` 구현
- [ ] `ctx.can_trade` 확인
- [ ] **`ctx.ohlcv` DataFrame 사용**
- [ ] **Indicator 모듈 import 및 사용**
- [ ] 리스크 기반 수량 계산 구현

### 권장

- [ ] `on_start()`, `on_stop()` 구현
- [ ] `on_error()` 구현
- [ ] `on_trade()` 구현 (Break-Even 등)
- [ ] 단위 테스트 작성

### secrets.yaml

- [ ] `strategy.module` 설정
- [ ] `strategy.class` 설정
- [ ] `quantity`는 설정하지 않음 (**중요**)

---

## 예제 전략

### AtrRiskManagedStrategy (권장)

`strategies/examples/atr_risk_strategy.py` 참조

- **OHLCV DataFrame 기반**
- **Indicator 모듈 사용** (`sma`, `atr`)
- ATR 기반 손절 라인
- 2% 룰 동적 수량 계산

### SmaCrossStrategy (교육용)

`strategies/examples/sma_cross.py` 참조

- **OHLCV DataFrame 기반**
- **Indicator 모듈 사용** (`sma`)
- 단순 SMA 크로스
- 고정 수량 (교육 목적)

---

## 문의

전략 개발 관련 문의는 이슈 트래커를 통해 등록해 주세요.
