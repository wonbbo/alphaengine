"""
ATR 기반 리스크 관리 전략

핵심 원칙:
1. 손절 라인은 2*ATR로 결정
2. 2% 룰 적용 - 총자산의 2%만 리스크에 노출
3. 50거래마다 자산 재평가 (Account Equity Reset)
4. R:R 1:1.5로 50% 부분 익절
5. 부분 익절 후 손절을 진입가로 이동 (Break-Even)
6. 나머지 50%는 반대 신호 또는 전략 판단으로 청산

리스크 관리 철학:
- 매매 수량은 secrets.yaml에서 설정하지 않음
- 전략 내부에서 리스크 기반으로 동적 계산
- RiskGuard는 최종 안전장치, 전략이 최종 책임

주의: 이 전략은 교육 목적의 예제입니다.
실제 거래에 사용하기 전에 충분한 백테스트가 필요합니다.
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
    """Average True Range 계산
    
    Args:
        bars: 캔들스틱 리스트 (최신이 마지막)
        period: ATR 기간
        
    Returns:
        ATR 값 또는 None (데이터 부족 시)
    """
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


def calculate_sma(bars: list[Bar], period: int) -> Decimal | None:
    """단순 이동평균 계산"""
    if len(bars) < period:
        return None
    
    closes = [bar.close for bar in bars[-period:]]
    return sum(closes) / Decimal(period)


class AtrRiskManagedStrategy(Strategy):
    """ATR 기반 리스크 관리 전략
    
    전략 로직:
    1. SMA 크로스로 진입 신호 감지
    2. 진입 시 ATR 기반 손절 라인 계산 (2*ATR)
    3. 2% 룰로 매매 수량 동적 계산
    4. R:R 1:1.5로 50% 부분 익절 설정
    5. 부분 익절 후 손절을 진입가로 이동
    6. 반대 신호 시 전체 포지션 청산
    
    리스크 관리:
    - account_equity: 50거래마다 재평가되는 기준 자산
    - risk_per_trade: 거래당 리스크 비율 (기본 2%)
    - atr_multiplier: 손절 거리 = ATR * multiplier (기본 2)
    - reward_ratio: 익절 = 손절거리 * ratio (기본 1.5)
    - partial_tp_ratio: 부분 익절 비율 (기본 0.5 = 50%)
    """
    
    @property
    def name(self) -> str:
        return "AtrRiskManaged"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "ATR-based Risk Management Strategy with 2% Rule"
    
    @property
    def default_params(self) -> dict[str, Any]:
        return {
            # ATR 손절 방식 파라미터 (전략별 고유)
            "atr_period": 14,                # ATR 기간
            "atr_multiplier": "2.0",         # 손절 = ATR × multiplier
            
            # 진입 조건 파라미터 (SMA 크로스)
            "fast_sma_period": 5,
            "slow_sma_period": 20,
            
            # 거래소 제약 (심볼별로 다름)
            "min_qty": "1",                  # 최소 주문 수량
            "qty_precision": 0,              # 수량 소수점 자릿수
            
            # 참고: risk_per_trade, reward_ratio, partial_tp_ratio, equity_reset_trades
            # 는 ConfigStore에서 조회 (ctx.risk_per_trade 등)
        }
    
    async def on_init(self, params: dict[str, Any]) -> None:
        """파라미터 초기화
        
        손절 방식별 파라미터는 전략 params에서 관리.
        리스크/리워드 공통 설정은 ctx.risk_config에서 동적 조회.
        """
        # ATR 손절 방식 파라미터 (전략 고유)
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = Decimal(str(params.get("atr_multiplier", "2.0")))
        
        # 진입 조건
        self.fast_sma_period = int(params.get("fast_sma_period", 5))
        self.slow_sma_period = int(params.get("slow_sma_period", 20))
        
        # 거래소 제약
        self.min_qty = Decimal(str(params.get("min_qty", "1")))
        self.qty_precision = int(params.get("qty_precision", 0))
        
        logger.info(
            f"{self.name} initialized: "
            f"ATR period={self.atr_period}, multiplier={self.atr_multiplier}, "
            f"SMA fast={self.fast_sma_period}, slow={self.slow_sma_period}"
        )
    
    async def on_start(self, ctx: StrategyTickContext) -> None:
        """전략 시작 - 상태 초기화
        
        DB에서 복원된 상태가 있으면 유지, 없으면 현재 잔고로 초기화.
        """
        state = ctx.strategy_state
        usdt = ctx.usdt_balance
        current_balance = usdt.total if usdt else Decimal("0")
        
        # DB에서 복원된 account_equity가 있으면 사용, 없으면 현재 잔고로 초기화
        if "account_equity" in state and state["account_equity"]:
            # 복원된 값이 문자열이면 Decimal로 변환
            restored_equity = state["account_equity"]
            if isinstance(restored_equity, str):
                restored_equity = Decimal(restored_equity)
            state["account_equity"] = restored_equity
            
            logger.info(
                f"{self.name} resumed with restored state: "
                f"equity={restored_equity}, "
                f"trades_since_reset={state.get('trade_count_since_reset', 0)}, "
                f"total_trades={state.get('total_trade_count', 0)}"
            )
        else:
            # 신규 시작: 현재 잔고로 초기화
            state["account_equity"] = current_balance
            state["trade_count_since_reset"] = 0
            state["total_trade_count"] = 0
            
            logger.info(
                f"{self.name} started fresh on {ctx.symbol}, "
                f"initial equity={current_balance}"
            )
        
        # SMA 크로스 상태 (항상 초기화)
        state["prev_fast_above"] = None
        
        # 포지션 상태 (항상 초기화 - 포지션은 거래소에서 확인)
        state["in_trade"] = False
        state["entry_price"] = None
        state["stop_loss_price"] = None
        state["initial_qty"] = None
        state["partial_tp_done"] = False
    
    async def on_tick(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """틱 처리 - 진입/청산 판단"""
        if not ctx.can_trade:
            return
        
        state = ctx.strategy_state
        
        # 데이터 충분성 검증
        required_bars = max(self.slow_sma_period, self.atr_period + 1)
        if len(ctx.bars) < required_bars:
            logger.debug(
                f"Not enough bars: {len(ctx.bars)} < {required_bars}"
            )
            return
        
        # 포지션이 없는 경우: 진입 신호 체크
        if not ctx.has_position:
            # 이전 거래 종료 후 상태 정리
            if state.get("in_trade"):
                self._clear_trade_state(state)
            
            # SMA 크로스 진입 신호 체크
            await self._check_entry_signal(ctx, emit, state)
        
        # 포지션이 있는 경우: 반대 신호 체크 (전체 청산)
        else:
            await self._check_exit_signal(ctx, emit, state)
    
    async def on_trade(
        self,
        trade: TradeEvent,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """체결 이벤트 콜백 - Break-Even 손절 조정"""
        state = ctx.strategy_state
        
        # AlphaEngine 주문만 처리
        if not trade.is_alphaengine_order:
            return
        
        # 부분 익절 체결 감지 → 손절을 진입가로 이동
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
        """주문 상태 변경 콜백"""
        state = ctx.strategy_state
        
        # 손절 체결 시 상태 초기화 및 거래 카운트
        if order.is_filled and order.is_stop_loss:
            self._increment_trade_count(ctx, state)
            self._clear_trade_state(state)
            logger.info(f"Stop loss hit at {order.avg_price}")
    
    async def _check_entry_signal(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """SMA 크로스 진입 신호 체크"""
        fast_sma = calculate_sma(ctx.bars, self.fast_sma_period)
        slow_sma = calculate_sma(ctx.bars, self.slow_sma_period)
        
        if fast_sma is None or slow_sma is None:
            return
        
        fast_above = fast_sma > slow_sma
        prev_fast_above = state.get("prev_fast_above")
        state["prev_fast_above"] = fast_above
        
        # 첫 틱이면 신호 없음
        if prev_fast_above is None:
            return
        
        # 골든 크로스 (매수 신호)
        if fast_above and not prev_fast_above:
            await self._enter_long(ctx, emit, state)
        
        # 데드 크로스 (매도 신호)
        elif not fast_above and prev_fast_above:
            await self._enter_short(ctx, emit, state)
    
    async def _check_exit_signal(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """반대 신호 체크 - 전체 청산"""
        fast_sma = calculate_sma(ctx.bars, self.fast_sma_period)
        slow_sma = calculate_sma(ctx.bars, self.slow_sma_period)
        
        if fast_sma is None or slow_sma is None:
            return
        
        fast_above = fast_sma > slow_sma
        position = ctx.position
        
        if not position:
            return
        
        # Long 포지션에서 데드 크로스 → 청산
        if position.is_long and not fast_above:
            logger.info("Exit signal: Dead cross while LONG")
            await self._close_all_and_cleanup(ctx, emit, state)
        
        # Short 포지션에서 골든 크로스 → 청산
        elif position.is_short and fast_above:
            logger.info("Exit signal: Golden cross while SHORT")
            await self._close_all_and_cleanup(ctx, emit, state)
    
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
        
        # ATR 계산
        atr = calculate_atr(ctx.bars, self.atr_period)
        if not atr:
            logger.warning("Cannot calculate ATR, skipping entry")
            return
        
        # ConfigStore에서 공통 리스크/리워드 설정 조회
        risk_per_trade = ctx.risk_per_trade
        reward_ratio = ctx.reward_ratio
        partial_tp_ratio = ctx.partial_tp_ratio
        
        # 손절 거리 및 손절가 계산 (atr_multiplier는 전략 파라미터)
        stop_distance = atr * self.atr_multiplier
        stop_loss_price = entry_price - stop_distance
        
        # 2% 룰로 수량 계산
        qty = self._calculate_position_size(
            account_equity=state["account_equity"],
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_per_trade=risk_per_trade,
        )
        
        if qty < self.min_qty:
            logger.warning(
                f"Calculated qty {qty} < min_qty {self.min_qty}, skipping"
            )
            return
        
        # 익절가 계산 (R:R 적용)
        take_profit_price = entry_price + (stop_distance * reward_ratio)
        partial_qty = (qty * partial_tp_ratio).quantize(
            Decimal(10) ** -self.qty_precision,
            rounding=ROUND_DOWN,
        )
        
        # 상태 저장
        state["in_trade"] = True
        state["entry_price"] = entry_price
        state["stop_loss_price"] = stop_loss_price
        state["initial_qty"] = qty
        state["partial_tp_done"] = False
        state["direction"] = "LONG"
        
        logger.info(
            f"LONG entry: qty={qty}, entry={entry_price}, "
            f"SL={stop_loss_price}, TP={take_profit_price}, "
            f"partial_qty={partial_qty}, ATR={atr}"
        )
        
        # 1. 진입
        await emit.place_order(
            side="BUY",
            order_type="MARKET",
            quantity=str(qty),
        )
        
        # 2. 손절 (전량)
        await emit.place_order(
            side="SELL",
            order_type="STOP_MARKET",
            quantity=str(qty),
            stop_price=str(stop_loss_price),
            reduce_only=True,
        )
        
        # 3. 부분 익절 (partial_qty)
        if partial_qty >= self.min_qty:
            await emit.place_order(
                side="SELL",
                order_type="LIMIT",
                quantity=str(partial_qty),
                price=str(take_profit_price),
                reduce_only=True,
            )
    
    async def _enter_short(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """Short 진입"""
        entry_price = ctx.current_price
        if not entry_price:
            return
        
        # ATR 계산
        atr = calculate_atr(ctx.bars, self.atr_period)
        if not atr:
            logger.warning("Cannot calculate ATR, skipping entry")
            return
        
        # ConfigStore에서 공통 리스크/리워드 설정 조회
        risk_per_trade = ctx.risk_per_trade
        reward_ratio = ctx.reward_ratio
        partial_tp_ratio = ctx.partial_tp_ratio
        
        # 손절 거리 및 손절가 계산 (Short: 손절은 위로, atr_multiplier는 전략 파라미터)
        stop_distance = atr * self.atr_multiplier
        stop_loss_price = entry_price + stop_distance
        
        # 2% 룰로 수량 계산
        qty = self._calculate_position_size(
            account_equity=state["account_equity"],
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_per_trade=risk_per_trade,
        )
        
        if qty < self.min_qty:
            logger.warning(
                f"Calculated qty {qty} < min_qty {self.min_qty}, skipping"
            )
            return
        
        # 익절가 계산 (R:R 적용, Short: 익절은 아래로)
        take_profit_price = entry_price - (stop_distance * reward_ratio)
        partial_qty = (qty * partial_tp_ratio).quantize(
            Decimal(10) ** -self.qty_precision,
            rounding=ROUND_DOWN,
        )
        
        # 상태 저장
        state["in_trade"] = True
        state["entry_price"] = entry_price
        state["stop_loss_price"] = stop_loss_price
        state["initial_qty"] = qty
        state["partial_tp_done"] = False
        state["direction"] = "SHORT"
        
        logger.info(
            f"SHORT entry: qty={qty}, entry={entry_price}, "
            f"SL={stop_loss_price}, TP={take_profit_price}, "
            f"partial_qty={partial_qty}, ATR={atr}"
        )
        
        # 1. 진입
        await emit.place_order(
            side="SELL",
            order_type="MARKET",
            quantity=str(qty),
        )
        
        # 2. 손절 (전량)
        await emit.place_order(
            side="BUY",
            order_type="STOP_MARKET",
            quantity=str(qty),
            stop_price=str(stop_loss_price),
            reduce_only=True,
        )
        
        # 3. 부분 익절 (partial_qty)
        if partial_qty >= self.min_qty:
            await emit.place_order(
                side="BUY",
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
        risk_per_trade: Decimal | None = None,
    ) -> Decimal:
        """2% 룰 기반 포지션 사이즈 계산
        
        공식:
            risk_amount = account_equity * risk_per_trade
            stop_distance = |entry_price - stop_loss_price|
            quantity = risk_amount / stop_distance
        
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
        
        # 리스크 금액 = 자산 * 리스크 비율
        risk_amount = account_equity * risk_ratio
        
        # 손절 거리 (절대값)
        stop_distance = abs(entry_price - stop_loss_price)
        
        if stop_distance == Decimal("0"):
            logger.warning("Stop distance is zero, cannot calculate size")
            return Decimal("0")
        
        # 수량 = 리스크 금액 / 손절 거리
        raw_qty = risk_amount / stop_distance
        
        # 소수점 자릿수 적용 (내림)
        qty = raw_qty.quantize(
            Decimal(10) ** -self.qty_precision,
            rounding=ROUND_DOWN,
        )
        
        return qty
    
    async def _move_stop_to_breakeven(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """손절을 진입가로 이동 (Break-Even)"""
        entry_price = state.get("entry_price")
        direction = state.get("direction")
        
        if not entry_price or not ctx.position:
            return
        
        remaining_qty = ctx.position.qty
        
        # 기존 손절 취소
        for order in ctx.open_orders:
            if order.order_type in ("STOP", "STOP_MARKET"):
                await emit.cancel_order(
                    exchange_order_id=order.exchange_order_id
                )
        
        # 새 손절 (진입가)
        side = "SELL" if direction == "LONG" else "BUY"
        
        await emit.place_order(
            side=side,
            order_type="STOP_MARKET",
            quantity=str(remaining_qty),
            stop_price=str(entry_price),
            reduce_only=True,
        )
        
        logger.info(
            f"SL moved to break-even: {entry_price}, remaining={remaining_qty}"
        )
    
    async def _close_all_and_cleanup(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
        state: dict[str, Any],
    ) -> None:
        """모든 주문 취소 + 포지션 청산 + 상태 정리"""
        # 모든 오픈 주문 취소
        await emit.cancel_all_orders()
        
        # 포지션 청산
        await emit.close_position(reduce_only=True)
        
        # 거래 카운트 및 상태 정리
        self._increment_trade_count(ctx, state)
        self._clear_trade_state(state)
        
        logger.info("Position closed and state cleared")
    
    def _increment_trade_count(
        self,
        ctx: StrategyTickContext,
        state: dict[str, Any],
    ) -> None:
        """거래 카운트 증가 및 자산 재평가"""
        state["trade_count_since_reset"] = state.get(
            "trade_count_since_reset", 0
        ) + 1
        state["total_trade_count"] = state.get("total_trade_count", 0) + 1
        
        # ConfigStore에서 자산 재평가 주기 조회
        equity_reset_trades = ctx.equity_reset_trades
        
        # 설정된 거래수마다 자산 재평가
        if state["trade_count_since_reset"] >= equity_reset_trades:
            usdt = ctx.usdt_balance
            new_equity = usdt.total if usdt else state["account_equity"]
            old_equity = state["account_equity"]
            
            state["account_equity"] = new_equity
            state["trade_count_since_reset"] = 0
            
            logger.info(
                f"Equity reset after {equity_reset_trades} trades: "
                f"{old_equity} → {new_equity} "
                f"(total trades: {state['total_trade_count']})"
            )
    
    def _clear_trade_state(self, state: dict[str, Any]) -> None:
        """거래 관련 상태 초기화"""
        state["in_trade"] = False
        state["entry_price"] = None
        state["stop_loss_price"] = None
        state["initial_qty"] = None
        state["partial_tp_done"] = False
        state["direction"] = None
    
    async def on_stop(self, ctx: StrategyTickContext) -> None:
        """전략 종료"""
        state = ctx.strategy_state
        total_trades = state.get("total_trade_count", 0)
        final_equity = state.get("account_equity", Decimal("0"))
        
        logger.info(
            f"{self.name} stopped. "
            f"Total trades: {total_trades}, Final equity: {final_equity}"
        )
    
    async def on_error(
        self,
        error: Exception,
        ctx: StrategyTickContext,
    ) -> bool:
        """에러 처리"""
        logger.error(f"{self.name} error: {error}")
        return True  # 에러 무시하고 계속 실행
