# AlphaEngine 전략 개발 가이드

이 문서는 AlphaEngine v2에서 신규 전략을 개발하고 적용하는 방법을 설명합니다.

## 목차

1. [전략 구조 개요](#전략-구조-개요)
2. [리스크 기반 수량 계산](#리스크-기반-수량-계산)
3. [신규 전략 생성](#신규-전략-생성)
4. [전략 등록 및 적용](#전략-등록-및-적용)
5. [전략 파라미터](#전략-파라미터)
6. [전략 컨텍스트](#전략-컨텍스트)
7. [이벤트 기반 콜백](#이벤트-기반-콜백)
8. [Multi-Timeframe 전략](#multi-timeframe-전략)
9. [Command 발행](#command-발행)
10. [테스트](#테스트)
11. [체크리스트](#체크리스트)

---

## 전략 구조 개요

AlphaEngine의 전략은 `Strategy` 추상 클래스를 상속받아 구현합니다.

```
strategies/
├── base.py                    # Strategy 추상 클래스, 타입 정의
├── __init__.py
└── examples/
    ├── sma_cross.py           # SMA 크로스 (교육용 단순 예제)
    ├── atr_risk_strategy.py   # ATR 기반 리스크 관리 전략 (권장)
    └── __init__.py
```

### 핵심 원칙

1. **전략은 거래소 API를 직접 호출하지 않음** - `CommandEmitter`를 통해 Command 발행
2. **상태는 `strategy_state`에 저장** - 틱 간 유지되는 상태
3. **거래 조건은 `ctx.can_trade` 확인** - 엔진 모드 검증
4. **매매 수량은 전략 내부에서 동적 계산** - 리스크 기반

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

이 방식의 장점:
- 손절 시 항상 총자산의 2%만 손실
- 변동성에 자동 적응 (ATR 큰 구간 = 적은 수량)
- 연속 손실에도 파산 확률 최소화

### 50거래 자산 재평가 (Account Equity Reset)

**핵심 원칙**: 2% 룰의 기준 자산은 50거래마다 재평가

| 시점 | 기준 자산 | 리스크 금액 (2%) |
|------|-----------|-----------------|
| 시작 | 10,000 USDT | 200 USDT |
| 25번째 거래 | 10,000 USDT (유지) | 200 USDT |
| 50번째 거래 후 | 12,000 USDT (재평가) | 240 USDT |
| 100번째 거래 후 | 9,000 USDT (재평가) | 180 USDT |

이 방식의 장점:
- 자주 재평가하면 변동 심함 → 50거래로 안정화
- 수익 시 점진적 복리 효과
- 손실 시 점진적 리스크 감소 (파산 방지)

### ATR 기반 손절 라인

**핵심 원칙**: 손절 거리 = ATR × Multiplier (보통 2)

```python
atr = calculate_atr(bars, period=14)  # 예: 1.5 USDT
stop_distance = atr * 2  # 3 USDT
stop_loss_price = entry_price - stop_distance  # Long의 경우
```

ATR의 장점:
- 시장 변동성에 자동 적응
- 변동성 큰 구간: 넓은 손절 → 휩쏘 방지
- 변동성 낮은 구간: 좁은 손절 → 빠른 손절

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

리스크/리워드 관련 **공통 설정**은 `config_store` 테이블의 "risk" 키에 저장되며, 전략에서 `ctx` 프로퍼티로 접근합니다.

| 설정 키 | 기본값 | 설명 | 접근 방식 |
|---------|--------|------|-----------|
| `risk_per_trade` | "0.02" | 거래당 리스크 비율 (2%) | `ctx.risk_per_trade` |
| `reward_ratio` | "1.5" | R:R = 1:reward_ratio | `ctx.reward_ratio` |
| `partial_tp_ratio` | "0.5" | 부분 익절 비율 (50%) | `ctx.partial_tp_ratio` |
| `equity_reset_trades` | 50 | 자산 재평가 주기 (거래 수) | `ctx.equity_reset_trades` |

이 값들은 Web UI에서 변경하면 실시간으로 전략에 반영됩니다.

### 전략 파라미터 (손절 방식별)

손절 방식에 따른 파라미터는 전략별로 다르므로 `secrets.yaml`의 `strategy.params`에서 관리합니다.

| 손절 방식 | 파라미터 예시 | 관리 위치 |
|-----------|---------------|-----------|
| ATR 기반 | `atr_period`, `atr_multiplier` | 전략 `params` |
| 퍼센트 기반 | `stop_percent` | 전략 `params` |
| 지지/저항 기반 | `buffer_ticks` | 전략 `params` |

### 전략 상태 저장 (Bot 재시작 유지)

50거래마다 재평가되는 `account_equity`와 거래 카운트는 DB에 저장되어 Bot 재시작 시에도 유지됩니다.

| 저장 항목 | 설명 |
|-----------|------|
| `account_equity` | 현재 기준 자산 |
| `trade_count_since_reset` | 마지막 재평가 이후 거래 수 |
| `total_trade_count` | 총 거래 수 |

**저장 시점**:
- 거래 종료 시 (손절/익절 체결)
- Bot 종료 시

**복원 시점**:
- Bot 시작 시 (`on_start` 호출 전)

### 구현 코드

```python
async def _enter_long(self, ctx: StrategyTickContext, emit: CommandEmitter, state: dict):
    """Long 진입 - ConfigStore + 전략 파라미터 혼용"""
    entry_price = ctx.current_price
    atr = calculate_atr(ctx.bars, self.atr_period)
    
    # ConfigStore에서 공통 리스크/리워드 설정 조회 (실시간 반영)
    risk_per_trade = ctx.risk_per_trade     # 2% 룰
    reward_ratio = ctx.reward_ratio          # R:R 비율
    partial_tp_ratio = ctx.partial_tp_ratio  # 부분 익절 비율
    
    # 손절 거리 계산 (atr_multiplier는 전략 파라미터)
    stop_distance = atr * self.atr_multiplier
    stop_loss_price = entry_price - stop_distance
    
    # 2% 룰로 수량 계산
    qty = self._calculate_position_size(
        account_equity=state["account_equity"],
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        risk_per_trade=risk_per_trade,  # ConfigStore 값 전달
    )
    
    # 익절가 계산
    take_profit_price = entry_price + (stop_distance * reward_ratio)
    partial_qty = qty * partial_tp_ratio
    
    # ... 주문 발행

def _calculate_position_size(
    self,
    account_equity: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
    risk_per_trade: Decimal | None = None,  # ConfigStore에서 전달
) -> Decimal:
    """2% 룰 기반 포지션 사이즈 계산
    
    Args:
        account_equity: 기준 자산 (50거래마다 재평가)
        entry_price: 진입가
        stop_loss_price: 손절가
        risk_per_trade: 거래당 리스크 비율 (ctx.risk_per_trade)
        
    Returns:
        매매 수량
    """
    # 리스크 비율 (ConfigStore 우선)
    risk_ratio = risk_per_trade or Decimal("0.02")
    
    # 리스크 금액 = 자산 × 리스크 비율
    risk_amount = account_equity * risk_ratio
    
    # 손절 거리 (절대값)
    stop_distance = abs(entry_price - stop_loss_price)
    
    if stop_distance == Decimal("0"):
        return Decimal("0")
    
    # 수량 = 리스크 금액 / 손절 거리
    raw_qty = risk_amount / stop_distance
    
    # 소수점 자릿수 적용 (내림)
    qty = raw_qty.quantize(
        Decimal(10) ** -self.qty_precision,
        rounding=ROUND_DOWN,
    )
    
    return qty
```

---

## 신규 전략 생성

### 전략 템플릿 (리스크 기반)

```python
# strategies/my_strategy.py

"""
My Custom Strategy

리스크 기반 수량 계산을 포함한 전략 템플릿.
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Any

from strategies.base import (
    Strategy,
    StrategyTickContext,
    CommandEmitter,
    Bar,
    TradeEvent,
    OrderEvent,
)

logger = logging.getLogger(__name__)


def calculate_atr(bars: list[Bar], period: int) -> Decimal | None:
    """Average True Range 계산"""
    if len(bars) < period + 1:
        return None
    
    true_ranges: list[Decimal] = []
    
    for i in range(-period, 0):
        current = bars[i]
        previous = bars[i - 1]
        
        high_low = current.high - current.low
        high_prev_close = abs(current.high - previous.close)
        low_prev_close = abs(current.low - previous.close)
        
        true_range = max(high_low, high_prev_close, low_prev_close)
        true_ranges.append(true_range)
    
    return sum(true_ranges) / Decimal(period)


class MyStrategy(Strategy):
    """리스크 기반 전략 템플릿
    
    핵심 기능:
    1. ATR 기반 손절 라인 계산
    2. 2% 룰로 수량 동적 계산
    3. 50거래마다 자산 재평가
    4. 부분 익절 후 Break-Even 손절
    """
    
    @property
    def name(self) -> str:
        return "MyStrategy"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Risk-managed strategy template"
    
    @property
    def default_params(self) -> dict[str, Any]:
        # 주의: quantity는 파라미터에 없음 (전략 내부에서 계산)
        return {
            # 리스크 관리
            "risk_per_trade": "0.02",       # 2% 룰
            "atr_period": 14,                # ATR 기간
            "atr_multiplier": "2.0",         # 손절 = 2*ATR
            "reward_ratio": "1.5",           # R:R 1:1.5
            "partial_tp_ratio": "0.5",       # 50% 부분 익절
            "equity_reset_trades": 50,       # 50거래마다 자산 재평가
            
            # 거래소 제약 (심볼별로 다름)
            "min_qty": "1",
            "qty_precision": 0,
        }
    
    async def on_init(self, params: dict[str, Any]) -> None:
        """파라미터 초기화"""
        self.risk_per_trade = Decimal(str(params.get("risk_per_trade", "0.02")))
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = Decimal(str(params.get("atr_multiplier", "2.0")))
        self.reward_ratio = Decimal(str(params.get("reward_ratio", "1.5")))
        self.partial_tp_ratio = Decimal(str(params.get("partial_tp_ratio", "0.5")))
        self.equity_reset_trades = int(params.get("equity_reset_trades", 50))
        
        self.min_qty = Decimal(str(params.get("min_qty", "1")))
        self.qty_precision = int(params.get("qty_precision", 0))
        
        logger.info(f"{self.name} initialized")
    
    async def on_start(self, ctx: StrategyTickContext) -> None:
        """전략 시작 - 상태 초기화"""
        state = ctx.strategy_state
        
        # 50거래 재평가용 기준 자산 설정
        usdt = ctx.usdt_balance
        initial_equity = usdt.total if usdt else Decimal("0")
        
        state["account_equity"] = initial_equity
        state["trade_count_since_reset"] = 0
        state["total_trade_count"] = 0
        
        # 포지션 상태
        state["in_trade"] = False
        state["entry_price"] = None
        state["stop_loss_price"] = None
        state["partial_tp_done"] = False
        
        logger.info(f"{self.name} started, equity={initial_equity}")
    
    async def on_tick(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """틱 처리"""
        if not ctx.can_trade:
            return
        
        state = ctx.strategy_state
        
        # 포지션 없음 → 진입 판단
        if not ctx.has_position:
            if state.get("in_trade"):
                self._clear_trade_state(state)
            
            if self._should_enter(ctx):
                await self._enter(ctx, emit, state)
        
        # 포지션 있음 → 청산 판단
        else:
            if self._should_exit(ctx):
                await self._close_all(ctx, emit, state)
    
    async def on_trade(
        self,
        trade: TradeEvent,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """체결 이벤트 - Break-Even 손절 조정"""
        state = ctx.strategy_state
        
        if not trade.is_alphaengine_order:
            return
        
        # 부분 익절 → 손절을 진입가로 이동
        if trade.is_reduce and trade.is_profitable:
            if not state.get("partial_tp_done"):
                state["partial_tp_done"] = True
                await self._move_stop_to_breakeven(ctx, emit, state)
    
    async def on_order_update(
        self,
        order: OrderEvent,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """주문 상태 변경 - 손절 체결 시 정리"""
        state = ctx.strategy_state
        
        if order.is_filled and order.is_stop_loss:
            self._increment_trade_count(ctx, state)
            self._clear_trade_state(state)
    
    def _should_enter(self, ctx: StrategyTickContext) -> bool:
        """진입 조건 (구현 필요)"""
        # TODO: 진입 로직 구현
        return False
    
    def _should_exit(self, ctx: StrategyTickContext) -> bool:
        """청산 조건 (구현 필요)"""
        # TODO: 청산 로직 구현
        return False
    
    async def _enter(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """진입 (Long 예시)"""
        entry_price = ctx.current_price
        if not entry_price:
            return
        
        # ATR 계산
        atr = calculate_atr(ctx.bars, self.atr_period)
        if not atr:
            return
        
        # 손절/익절가 계산
        stop_distance = atr * self.atr_multiplier
        stop_loss_price = entry_price - stop_distance
        take_profit_price = entry_price + (stop_distance * self.reward_ratio)
        
        # 2% 룰로 수량 계산
        qty = self._calculate_position_size(
            account_equity=state["account_equity"],
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
        )
        
        if qty < self.min_qty:
            logger.warning(f"qty {qty} < min_qty {self.min_qty}")
            return
        
        partial_qty = (qty * self.partial_tp_ratio).quantize(
            Decimal(10) ** -self.qty_precision,
            rounding=ROUND_DOWN,
        )
        
        # 상태 저장
        state["in_trade"] = True
        state["entry_price"] = entry_price
        state["stop_loss_price"] = stop_loss_price
        state["initial_qty"] = qty
        state["partial_tp_done"] = False
        
        # 1. 진입
        await emit.place_order(
            side="BUY",
            order_type="MARKET",
            quantity=str(qty),
        )
        
        # 2. 손절
        await emit.place_order(
            side="SELL",
            order_type="STOP_MARKET",
            quantity=str(qty),
            stop_price=str(stop_loss_price),
            reduce_only=True,
        )
        
        # 3. 부분 익절
        if partial_qty >= self.min_qty:
            await emit.place_order(
                side="SELL",
                order_type="LIMIT",
                quantity=str(partial_qty),
                price=str(take_profit_price),
                reduce_only=True,
            )
    
    def _calculate_position_size(
        self,
        account_equity: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> Decimal:
        """2% 룰 기반 포지션 사이즈 계산"""
        risk_amount = account_equity * self.risk_per_trade
        stop_distance = abs(entry_price - stop_loss_price)
        
        if stop_distance == Decimal("0"):
            return Decimal("0")
        
        raw_qty = risk_amount / stop_distance
        
        return raw_qty.quantize(
            Decimal(10) ** -self.qty_precision,
            rounding=ROUND_DOWN,
        )
    
    async def _move_stop_to_breakeven(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """손절을 진입가로 이동"""
        entry_price = state.get("entry_price")
        if not entry_price or not ctx.position:
            return
        
        # 기존 손절 취소
        for order in ctx.open_orders:
            if order.order_type in ("STOP", "STOP_MARKET"):
                await emit.cancel_order(exchange_order_id=order.exchange_order_id)
        
        # 새 손절 (진입가)
        await emit.place_order(
            side="SELL",
            order_type="STOP_MARKET",
            quantity=str(ctx.position.qty),
            stop_price=str(entry_price),
            reduce_only=True,
        )
        
        logger.info(f"SL moved to break-even: {entry_price}")
    
    async def _close_all(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """전체 청산"""
        await emit.cancel_all_orders()
        await emit.close_position(reduce_only=True)
        self._increment_trade_count(ctx, state)
        self._clear_trade_state(state)
    
    def _increment_trade_count(
        self,
        ctx: StrategyTickContext,
        state: dict[str, Any],
    ) -> None:
        """거래 카운트 및 50거래 재평가"""
        state["trade_count_since_reset"] = state.get("trade_count_since_reset", 0) + 1
        state["total_trade_count"] = state.get("total_trade_count", 0) + 1
        
        if state["trade_count_since_reset"] >= self.equity_reset_trades:
            usdt = ctx.usdt_balance
            new_equity = usdt.total if usdt else state["account_equity"]
            old_equity = state["account_equity"]
            
            state["account_equity"] = new_equity
            state["trade_count_since_reset"] = 0
            
            logger.info(f"Equity reset: {old_equity} → {new_equity}")
    
    def _clear_trade_state(self, state: dict[str, Any]) -> None:
        """거래 상태 초기화"""
        state["in_trade"] = False
        state["entry_price"] = None
        state["stop_loss_price"] = None
        state["initial_qty"] = None
        state["partial_tp_done"] = False
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
    # 리스크 관리 (선택)
    risk_per_trade: "0.02"
    atr_period: 14
    atr_multiplier: "2.0"
    equity_reset_trades: 50
    
    # 거래소 제약 (심볼별로 확인)
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
        # === 리스크 관리 ===
        "risk_per_trade": "0.02",       # 거래당 리스크 비율
        "atr_period": 14,                # ATR 기간
        "atr_multiplier": "2.0",         # 손절 = ATR × multiplier
        "reward_ratio": "1.5",           # 익절 = 손절거리 × ratio
        "partial_tp_ratio": "0.5",       # 부분 익절 비율
        "equity_reset_trades": 50,       # 자산 재평가 주기
        
        # === 전략 고유 ===
        "signal_period": 20,             # 신호 판단 기간
        # ... 전략별 파라미터 ...
        
        # === 거래소 제약 ===
        "min_qty": "1",                  # 최소 주문 수량
        "qty_precision": 0,              # 수량 소수점
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
| `ctx.bars` | `list[Bar]` | 캔들 데이터 |
| `ctx.current_price` | `Decimal \| None` | 현재가 |
| `ctx.position` | `Position \| None` | 현재 포지션 |
| `ctx.has_position` | `bool` | 포지션 보유 여부 |
| `ctx.balances` | `dict[str, Balance]` | 잔고 |
| `ctx.usdt_balance` | `Balance \| None` | USDT 잔고 |
| `ctx.open_orders` | `list[OpenOrder]` | 미체결 주문 |
| `ctx.strategy_state` | `dict` | 틱 간 유지되는 상태 |
| `ctx.can_trade` | `bool` | 거래 가능 여부 |
| `ctx.market_data` | `MarketDataProvider` | MTF용 |

### 잔고 조회 (자산 재평가용)

```python
usdt = ctx.usdt_balance
if usdt:
    total_equity = usdt.total  # free + locked
    free_equity = usdt.free    # 사용 가능
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

### OrderEvent

주문 상태 변경 시 `on_order_update()` 콜백으로 전달:

```python
@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    client_order_id: str | None
    symbol: str
    status: str            # NEW, FILLED, CANCELED, REJECTED, EXPIRED
    order_type: str
    side: str
    price: Decimal | None
    stop_price: Decimal | None
    original_qty: Decimal
    executed_qty: Decimal
    avg_price: Decimal
    reduce_only: bool
    close_position: bool
    timestamp: datetime
    
    # 주요 속성
    is_filled: bool        # 완전 체결
    is_stop_loss: bool     # 손절 주문
    is_take_profit: bool   # 익절 주문
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

async def on_order_update(
    self,
    order: OrderEvent,
    ctx: StrategyTickContext,
    emit: CommandEmitter,
) -> None:
    """손절 체결 시 정리"""
    if order.is_filled and order.is_stop_loss:
        self._increment_trade_count(ctx, ctx.strategy_state)
        self._clear_trade_state(ctx.strategy_state)
```

---

## Multi-Timeframe 전략

### ctx.get_bars() 사용

```python
async def on_tick(self, ctx: StrategyTickContext, emit: CommandEmitter) -> None:
    bars_5m = ctx.bars                          # 기본 5분봉
    bars_15m = await ctx.get_bars("15m", limit=50)
    bars_1h = await ctx.get_bars("1h", limit=24)
    bars_4h = await ctx.get_bars("4h", limit=30)
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

### 단위 테스트

```python
# tests/unit/strategies/test_my_strategy.py

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from strategies.my_strategy import MyStrategy, calculate_atr
from strategies.base import StrategyTickContext, Bar


class TestPositionSizing:
    @pytest.fixture
    def strategy(self) -> MyStrategy:
        s = MyStrategy()
        # 파라미터 설정
        s.risk_per_trade = Decimal("0.02")
        s.qty_precision = 0
        return s
    
    def test_calculate_position_size(self, strategy: MyStrategy) -> None:
        qty = strategy._calculate_position_size(
            account_equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("97"),
        )
        
        # risk_amount = 10000 * 0.02 = 200
        # stop_distance = |100 - 97| = 3
        # qty = 200 / 3 = 66.66... → 66 (내림)
        assert qty == Decimal("66")
```

### 테스트 실행

```bash
.venv\Scripts\python.exe -m pytest tests/unit/strategies/ -v
```

---

## 체크리스트

### 필수

- [ ] `Strategy` 클래스 상속
- [ ] `name`, `version`, `default_params` 구현
- [ ] `on_init()`, `on_tick()` 구현
- [ ] `ctx.can_trade` 확인
- [ ] 리스크 기반 수량 계산 구현 (`_calculate_position_size`)
- [ ] ATR 또는 다른 방식으로 손절 라인 계산
- [ ] 50거래 자산 재평가 구현

### 권장

- [ ] `on_start()`, `on_stop()` 구현
- [ ] `on_error()` 구현
- [ ] `on_trade()` 구현 (Break-Even 등)
- [ ] `on_order_update()` 구현
- [ ] 단위 테스트 작성

### secrets.yaml

- [ ] `strategy.module` 설정
- [ ] `strategy.class` 설정
- [ ] `quantity`는 설정하지 않음 (**중요**)
- [ ] 거래소 제약 파라미터 확인 (`min_qty`, `qty_precision`)

### 배포

- [ ] Testnet에서 충분히 테스트
- [ ] 로그 확인하여 수량 계산 검증
- [ ] Production 전환 전 `mode: production` 확인

---

## 예제 전략

### AtrRiskManagedStrategy (권장)

`strategies/examples/atr_risk_strategy.py` 참조

- ATR 기반 손절 라인
- 2% 룰 동적 수량 계산
- 50거래 자산 재평가
- 부분 익절 후 Break-Even

### SmaCrossStrategy (교육용)

`strategies/examples/sma_cross.py` 참조

- 단순 SMA 크로스
- 고정 수량 (교육 목적)
- 실제 운용에는 부적합

---

## 문의

전략 개발 관련 문의는 이슈 트래커를 통해 등록해 주세요.
