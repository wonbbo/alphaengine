"""
Breakout 전략 (스켈레톤)

브레이크아웃(캔들 high/low 돌파) 기반 진입/청산 스켈레톤.
실제 거래용이 아닌, 입력 변수 검증 로그와 모든 이벤트 콜백을 갖춘 구조만 제공.
내부 로직을 채우면 실제 운용 가능한 클래스로 확장 가능.

제공 콜백:
- on_init, on_start, on_tick, on_stop, on_error
- on_trade (계약체결, 부분 익절, 손절 등)
- on_order_update (주문 상태 변경)
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Any

import pandas as pd

from strategies.base import (
    Strategy,
    StrategyTickContext,
    CommandEmitter,
    TradeEvent,
    OrderEvent,
)
from strategies.indicators import atr

logger = logging.getLogger(__name__)


class BreakoutStrategy(Strategy):
    """브레이크아웃 전략 (스켈레톤)

    구조:
    - lookback 기간 고가/저가 돌파 시 Long/Short 진입
    - ATR 기반 손절, 리스크 기반 수량
    - 부분 익절 후 Break-Even 손절 등 (이벤트 콜백에서 처리)

    실제 매매는 하지 않고, 파라미터/컨텍스트 검증 로그와
    모든 이벤트 콜백을 구현해 두었음. 내부만 채우면 운용 가능.
    """

    @property
    def name(self) -> str:
        return "CE Breakout"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Chandelier Exit based reakout strategy"

    @property
    def default_params(self) -> dict[str, Any]:
        return {
            # 브레이크아웃 진입 조건
            "lookback_period": 20,
            # ATR 손절
            "atr_period": 14,
            "atr_multiplier": "2.0",
            # 거래소 제약
            "min_qty": "1",
            "qty_precision": 0,
        }

    # -------------------------------------------------------------------------
    # 생명주기: on_init, on_start, on_stop, on_error
    # -------------------------------------------------------------------------

    async def on_init(self, params: dict[str, Any]) -> None:
        """파라미터 초기화 및 검증 로그"""
        self.lookback_period = int(params.get("lookback_period", 20))
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = Decimal(str(params.get("atr_multiplier", "2.0")))
        self.min_qty = Decimal(str(params.get("min_qty", "1")))
        self.qty_precision = int(params.get("qty_precision", 0))

        # 검증 로그: 입력 변수
        logger.info(
            f"[BreakoutStrategy] on_init: lookback_period={self.lookback_period}, "
            f"atr_period={self.atr_period}, atr_multiplier={self.atr_multiplier}, "
            f"min_qty={self.min_qty}, qty_precision={self.qty_precision}"
        )
        if self.lookback_period < 2:
            logger.warning("[BreakoutStrategy] lookback_period < 2 may cause insufficient data")
        if self.atr_period < 1:
            logger.warning("[BreakoutStrategy] atr_period < 1 is invalid")
        if self.atr_multiplier <= Decimal("0"):
            logger.warning("[BreakoutStrategy] atr_multiplier should be positive")

    async def on_start(self, ctx: StrategyTickContext) -> None:
        """전략 시작 - 상태 초기화 및 검증 로그"""
        state = ctx.strategy_state
        usdt = ctx.usdt_balance
        current_balance = usdt.total if usdt else Decimal("0")

        # 복원된 상태가 있으면 사용
        if "account_equity" in state and state["account_equity"]:
            restored = state["account_equity"]
            if isinstance(restored, str):
                restored = Decimal(restored)
            state["account_equity"] = restored
            logger.info(
                f"[BreakoutStrategy] on_start (resumed): symbol={ctx.symbol}, "
                f"account_equity={restored}, trade_count_since_reset={state.get('trade_count_since_reset', 0)}"
            )
        else:
            state["account_equity"] = current_balance
            state["trade_count_since_reset"] = 0
            state["total_trade_count"] = 0
            logger.info(
                f"[BreakoutStrategy] on_start (fresh): symbol={ctx.symbol}, initial equity={current_balance}"
            )

        state["prev_breakout_high"] = None
        state["prev_breakout_low"] = None
        state["in_trade"] = False
        state["entry_price"] = None
        state["stop_loss_price"] = None
        state["initial_qty"] = None
        state["partial_tp_done"] = False
        state["direction"] = None

    async def on_tick(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """틱 처리 - 진입/청산 판단 (스켈레톤: 검증 로그 + 최소 구조)"""
        # 거래 가능 여부 검증 로그
        if not ctx.can_trade:
            logger.debug("[BreakoutStrategy] on_tick: can_trade=False, skip")
            return

        ohlcv = ctx.ohlcv
        state = ctx.strategy_state

        required_rows = max(self.lookback_period, self.atr_period + 1)
        if len(ohlcv) < required_rows:
            logger.debug(
                f"[BreakoutStrategy] on_tick: insufficient OHLCV rows "
                f"({len(ohlcv)} < {required_rows}), skip"
            )
            return

        # 검증 로그: 컨텍스트 요약 (주기적으로는 debug 수준)
        logger.debug(
            f"[BreakoutStrategy] on_tick: symbol={ctx.symbol}, has_position={ctx.has_position}, "
            f"current_price={ctx.current_price}, ohlcv_rows={len(ohlcv)}"
        )

        if not ctx.has_position:
            if state.get("in_trade"):
                self._clear_trade_state(state)
            await self._check_breakout_entry(ctx, emit, state)
        else:
            await self._check_breakout_exit(ctx, emit, state)

    async def on_stop(self, ctx: StrategyTickContext) -> None:
        """전략 종료"""
        state = ctx.strategy_state
        total_trades = state.get("total_trade_count", 0)
        final_equity = state.get("account_equity", Decimal("0"))
        logger.info(
            f"[BreakoutStrategy] on_stop: total_trades={total_trades}, final_equity={final_equity}"
        )

    async def on_error(
        self,
        error: Exception,
        ctx: StrategyTickContext,
    ) -> bool:
        """에러 처리 - 로그 후 계속 실행할지 여부 반환"""
        logger.error(f"[BreakoutStrategy] on_error: {error}", exc_info=True)
        return True  # True: 복구 후 계속 실행

    # -------------------------------------------------------------------------
    # 이벤트 콜백: on_trade (계약체결, 부분 익절, 손절 등), on_order_update
    # -------------------------------------------------------------------------

    async def on_trade(
        self,
        trade: TradeEvent,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """체결 이벤트 - 계약체결/부분 익절/손절 등 구분하여 로그"""
        logger.info(
            f"[BreakoutStrategy] on_trade: trade_id={trade.trade_id}, order_id={trade.order_id}, "
            f"side={trade.side}, price={trade.price}, quantity={trade.quantity}, "
            f"realized_pnl={trade.realized_pnl}, is_reduce={trade.is_reduce}, "
            f"is_profitable={trade.is_profitable}, is_alphaengine_order={trade.is_alphaengine_order}"
        )

        if not trade.is_alphaengine_order:
            logger.debug("[BreakoutStrategy] on_trade: not AlphaEngine order, skip logic")
            return

        state = ctx.strategy_state

        # 청산 체결이 아닌 경우: 진입 체결
        if not trade.is_reduce:
            logger.info("[BreakoutStrategy] on_trade: 진입 체결 (entry fill)")
            return

        # 청산 체결: 부분 익절 vs 손절 vs 기타
        if trade.is_profitable:
            if not state.get("partial_tp_done"):
                logger.info("[BreakoutStrategy] on_trade: 부분 익절 체결 (partial take profit)")
                state["partial_tp_done"] = True
                # TODO: 손절을 진입가로 이동 (Break-Even)
                # await self._move_stop_to_breakeven(ctx, emit, state)
            else:
                logger.info("[BreakoutStrategy] on_trade: 나머지 익절 체결 (remaining take profit)")
        else:
            logger.info("[BreakoutStrategy] on_trade: 손절 체결 (stop loss)")
            self._increment_trade_count(ctx, state)
            self._clear_trade_state(state)

    async def on_order_update(
        self,
        order: OrderEvent,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """주문 상태 변경 - NEW/FILLED/CANCELED/REJECTED/EXPIRED 등 로그"""
        logger.info(
            f"[BreakoutStrategy] on_order_update: order_id={order.order_id}, status={order.status}, "
            f"order_type={order.order_type}, side={order.side}, "
            f"executed_qty={order.executed_qty}, remaining_qty={order.remaining_qty}, "
            f"is_stop_loss={order.is_stop_loss}, is_take_profit={order.is_take_profit}"
        )

        state = ctx.strategy_state

        if order.is_filled and order.is_stop_loss:
            self._increment_trade_count(ctx, state)
            self._clear_trade_state(state)
            logger.info(f"[BreakoutStrategy] on_order_update: 손절 주문 체결 at avg_price={order.avg_price}")

        if order.is_filled and order.is_take_profit:
            logger.info(f"[BreakoutStrategy] on_order_update: 익절 주문 체결 at avg_price={order.avg_price}")

        if order.is_canceled or order.is_rejected or order.is_expired:
            logger.info(
                f"[BreakoutStrategy] on_order_update: 주문 종료 status={order.status} "
                f"(canceled={order.is_canceled}, rejected={order.is_rejected}, expired={order.is_expired})"
            )

    # -------------------------------------------------------------------------
    # 진입/청산 스켈레톤 (내부 채우면 실제 운용 가능)
    # -------------------------------------------------------------------------

    async def _check_breakout_entry(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """브레이크아웃 진입 신호 체크 (스켈레톤)"""
        ohlcv = ctx.ohlcv
        n = self.lookback_period
        if len(ohlcv) < n + 1:
            return

        # lookback 구간 고가/저가
        recent_high = ohlcv["high"].iloc[-n-1:-1].max()
        recent_low = ohlcv["low"].iloc[-n-1:-1].min()
        close = ohlcv["close"].iloc[-1]

        prev_high = state.get("prev_breakout_high")
        prev_low = state.get("prev_breakout_low")
        state["prev_breakout_high"] = recent_high
        state["prev_breakout_low"] = recent_low

        if prev_high is None or prev_low is None:
            return

        # 상단 돌파 → Long, 하단 돌파 → Short (스켈레톤: 로그만)
        long_breakout = close > recent_high
        short_breakout = close < recent_low

        if long_breakout:
            logger.info(
                f"[BreakoutStrategy] breakout signal LONG: close={close} > recent_high={recent_high}"
            )
            # TODO: await self._enter_long(ctx, emit, state)
        elif short_breakout:
            logger.info(
                f"[BreakoutStrategy] breakout signal SHORT: close={close} < recent_low={recent_low}"
            )
            # TODO: await self._enter_short(ctx, emit, state)

    async def _check_breakout_exit(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """브레이크아웃 청산 신호 체크 (스켈레톤)"""
        # TODO: 반대 돌파 또는 추세 이탈 시 청산
        logger.debug("[BreakoutStrategy] _check_breakout_exit: placeholder")

    async def _enter_long(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """Long 진입 (스켈레톤) - 내부 채우면 실제 주문 가능"""
        entry_price = ctx.current_price
        if not entry_price:
            logger.warning("[BreakoutStrategy] _enter_long: no current_price")
            return

        atr_series = atr(ctx.ohlcv, {"period": self.atr_period})
        atr_value = atr_series.iloc[-1]
        if pd.isna(atr_value):
            logger.warning("[BreakoutStrategy] _enter_long: ATR NaN")
            return

        atr_decimal = Decimal(str(atr_value))
        stop_distance = atr_decimal * self.atr_multiplier
        stop_loss_price = entry_price - stop_distance

        risk_per_trade = ctx.risk_per_trade
        qty = self._calculate_position_size(
            account_equity=state["account_equity"],
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_per_trade=risk_per_trade,
        )

        if qty < self.min_qty:
            logger.warning(f"[BreakoutStrategy] _enter_long: qty={qty} < min_qty={self.min_qty}")
            return

        logger.info(
            f"[BreakoutStrategy] _enter_long (skeleton): entry={entry_price}, sl={stop_loss_price}, qty={qty}"
        )
        state["in_trade"] = True
        state["entry_price"] = entry_price
        state["stop_loss_price"] = stop_loss_price
        state["initial_qty"] = qty
        state["partial_tp_done"] = False
        state["direction"] = "LONG"

        # 실제 주문 시 아래 주석 해제 후 사용
        # await emit.place_order(side="BUY", order_type="MARKET", quantity=str(qty))
        # await emit.place_order(
        #     side="SELL", order_type="STOP_MARKET", quantity=str(qty),
        #     stop_price=str(stop_loss_price), reduce_only=True,
        # )

    async def _enter_short(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """Short 진입 (스켈레톤)"""
        entry_price = ctx.current_price
        if not entry_price:
            return
        atr_series = atr(ctx.ohlcv, {"period": self.atr_period})
        atr_value = atr_series.iloc[-1]
        if pd.isna(atr_value):
            return
        atr_decimal = Decimal(str(atr_value))
        stop_distance = atr_decimal * self.atr_multiplier
        stop_loss_price = entry_price + stop_distance
        qty = self._calculate_position_size(
            account_equity=state["account_equity"],
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_per_trade=ctx.risk_per_trade,
        )
        if qty < self.min_qty:
            return
        state["in_trade"] = True
        state["entry_price"] = entry_price
        state["stop_loss_price"] = stop_loss_price
        state["initial_qty"] = qty
        state["partial_tp_done"] = False
        state["direction"] = "SHORT"
        logger.info(
            f"[BreakoutStrategy] _enter_short (skeleton): entry={entry_price}, sl={stop_loss_price}, qty={qty}"
        )

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

    def _increment_trade_count(
        self,
        ctx: StrategyTickContext,
        state: dict[str, Any],
    ) -> None:
        """거래 카운트 증가 및 자산 재평가"""
        state["trade_count_since_reset"] = state.get("trade_count_since_reset", 0) + 1
        state["total_trade_count"] = state.get("total_trade_count", 0) + 1
        if state["trade_count_since_reset"] >= ctx.equity_reset_trades:
            usdt = ctx.usdt_balance
            new_equity = usdt.total if usdt else state["account_equity"]
            state["account_equity"] = new_equity
            state["trade_count_since_reset"] = 0
            logger.info(
                f"[BreakoutStrategy] equity reset after {ctx.equity_reset_trades} trades: {new_equity}"
            )

    def _clear_trade_state(self, state: dict[str, Any]) -> None:
        """거래 관련 상태 초기화"""
        state["in_trade"] = False
        state["entry_price"] = None
        state["stop_loss_price"] = None
        state["initial_qty"] = None
        state["partial_tp_done"] = False
        state["direction"] = None
