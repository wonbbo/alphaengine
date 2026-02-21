"""
SMA Cross Strategy (교육용 단순 예제)

단순 이동평균 교차 전략.
빠른 SMA가 느린 SMA를 상향 돌파하면 매수,
하향 돌파하면 매도.

주의: 
- 이 전략은 교육 목적의 단순 예제입니다.
- 고정 수량을 사용하는 단순한 구조입니다.
- 실제 운용 시에는 AtrRiskManagedStrategy처럼 
  리스크 기반 수량 계산을 사용하세요.
"""

import logging
from typing import Any

from strategies.base import Strategy, StrategyTickContext, CommandEmitter
from strategies.indicators import sma

logger = logging.getLogger(__name__)


class SmaCrossStrategy(Strategy):
    """SMA 크로스 전략 (교육용 단순 예제)
    
    이 전략은 고정 수량을 사용하는 단순한 예제입니다.
    실제 운용 시에는 AtrRiskManagedStrategy를 참조하여
    리스크 기반 수량 계산을 사용하세요.
    
    전략 로직:
    1. 빠른 SMA (기본 5)와 느린 SMA (기본 20) 계산
    2. 빠른 SMA > 느린 SMA 이고 이전에는 반대였다면 → 매수 신호
    3. 빠른 SMA < 느린 SMA 이고 이전에는 반대였다면 → 매도 신호
    4. 포지션이 있으면 반대 신호 발생 시 청산 후 반대 진입
    
    파라미터:
    - fast_period: 빠른 SMA 기간 (기본 5)
    - slow_period: 느린 SMA 기간 (기본 20)
    - fixed_quantity: 고정 주문 수량 (기본 "10") - 교육용
    - use_market_order: 시장가 주문 사용 (기본 True)
    """
    
    @property
    def name(self) -> str:
        return "SmaCross"
    
    @property
    def version(self) -> str:
        return "2.0.0"
    
    @property
    def description(self) -> str:
        return "Simple Moving Average Crossover Strategy (Educational)"
    
    @property
    def default_params(self) -> dict[str, Any]:
        return {
            "fast_period": 5,
            "slow_period": 20,
            "fixed_quantity": "10",
            "use_market_order": True,
        }
    
    async def on_init(self, params: dict[str, Any]) -> None:
        """초기화"""
        self.fast_period = int(params.get("fast_period", 5))
        self.slow_period = int(params.get("slow_period", 20))
        self.fixed_quantity = str(params.get("fixed_quantity", "10"))
        self.use_market_order = bool(params.get("use_market_order", True))
        
        logger.info(
            f"SmaCross initialized: fast={self.fast_period}, slow={self.slow_period}",
        )
        logger.warning(
            "SmaCross uses fixed quantity. For production, use risk-based sizing."
        )
    
    async def on_start(self, ctx: StrategyTickContext) -> None:
        """시작 시 상태 초기화"""
        ctx.strategy_state["prev_fast_above"] = None
        ctx.strategy_state["signal_count"] = 0
        
        logger.info(f"SmaCross started on {ctx.symbol}")
    
    async def on_tick(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """틱 처리"""
        # 거래 불가 상태 체크
        if not ctx.can_trade:
            logger.debug("Engine not in RUNNING mode, skipping tick")
            return
        
        ohlcv = ctx.ohlcv
        
        # 충분한 데이터 확인
        if len(ohlcv) < self.slow_period:
            logger.debug(
                f"Not enough OHLCV data: {len(ohlcv)} < {self.slow_period}",
            )
            return
        
        # SMA 계산 (indicator 모듈 사용)
        fast_sma_series = sma(ohlcv, {"period": self.fast_period})
        slow_sma_series = sma(ohlcv, {"period": self.slow_period})
        
        # 최신 값 가져오기
        fast_sma_value = fast_sma_series.iloc[-1]
        slow_sma_value = slow_sma_series.iloc[-1]
        
        # NaN 체크
        if fast_sma_value != fast_sma_value or slow_sma_value != slow_sma_value:
            return
        
        # 현재 상태
        fast_above = fast_sma_value > slow_sma_value
        
        # 이전 상태 조회
        prev_fast_above = ctx.strategy_state.get("prev_fast_above")
        
        # 상태 저장
        ctx.strategy_state["prev_fast_above"] = fast_above
        
        # 첫 틱이면 신호 없음
        if prev_fast_above is None:
            logger.debug(f"First tick, fast_sma={fast_sma_value:.4f}, slow_sma={slow_sma_value:.4f}")
            return
        
        # 교차 감지
        if fast_above and not prev_fast_above:
            # 골든 크로스 (매수 신호)
            await self._handle_buy_signal(ctx, emit)
            ctx.strategy_state["signal_count"] = ctx.strategy_state.get("signal_count", 0) + 1
            
        elif not fast_above and prev_fast_above:
            # 데드 크로스 (매도 신호)
            await self._handle_sell_signal(ctx, emit)
            ctx.strategy_state["signal_count"] = ctx.strategy_state.get("signal_count", 0) + 1
    
    async def _handle_buy_signal(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """매수 신호 처리"""
        logger.info(
            f"BUY signal: {ctx.symbol} @ {ctx.current_price}",
            extra={"symbol": ctx.symbol},
        )
        
        # 숏 포지션이 있으면 먼저 청산
        if ctx.has_position and ctx.position and ctx.position.is_short:
            logger.info("Closing short position before buy")
            await emit.close_position(reduce_only=True)
        
        # 매수 주문 (고정 수량 - 교육용)
        order_type = "MARKET" if self.use_market_order else "LIMIT"
        
        await emit.place_order(
            side="BUY",
            order_type=order_type,
            quantity=self.fixed_quantity,
            price=ctx.current_price if order_type == "LIMIT" else None,
        )
    
    async def _handle_sell_signal(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """매도 신호 처리"""
        logger.info(
            f"SELL signal: {ctx.symbol} @ {ctx.current_price}",
            extra={"symbol": ctx.symbol},
        )
        
        # 롱 포지션이 있으면 먼저 청산
        if ctx.has_position and ctx.position and ctx.position.is_long:
            logger.info("Closing long position before sell")
            await emit.close_position(reduce_only=True)
        
        # 매도 주문 (고정 수량 - 교육용)
        order_type = "MARKET" if self.use_market_order else "LIMIT"
        
        await emit.place_order(
            side="SELL",
            order_type=order_type,
            quantity=self.fixed_quantity,
            price=ctx.current_price if order_type == "LIMIT" else None,
        )
    
    async def on_stop(self, ctx: StrategyTickContext) -> None:
        """종료"""
        signal_count = ctx.strategy_state.get("signal_count", 0)
        logger.info(
            f"SmaCross stopped. Total signals: {signal_count}",
        )
    
    async def on_error(self, error: Exception, ctx: StrategyTickContext) -> bool:
        """에러 처리"""
        logger.error(
            f"SmaCross error: {error}",
            extra={"symbol": ctx.symbol},
        )
        return True
