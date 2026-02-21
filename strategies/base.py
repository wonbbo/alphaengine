"""
Strategy Interface

전략 플러그인 인터페이스 정의.
모든 전략은 이 인터페이스를 구현해야 함.

핵심 원칙:
1. 전략은 거래소 API를 직접 호출하지 않음
2. 전략은 읽기 전용 컨텍스트를 받음
3. 전략은 Command를 통해서만 행위 요청
4. 전략 상태는 strategy_state 딕셔너리로 관리
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import pandas as pd

from core.types import Scope


@dataclass(frozen=True)
class Bar:
    """캔들스틱 데이터"""
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    
    @property
    def ohlc(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """OHLC 튜플 반환"""
        return self.open, self.high, self.low, self.close


@dataclass(frozen=True)
class Position:
    """포지션 정보 (읽기 전용)"""
    symbol: str
    side: str | None  # LONG, SHORT, None (FLAT)
    qty: Decimal
    entry_price: Decimal
    unrealized_pnl: Decimal
    leverage: int
    margin_type: str
    
    @property
    def is_flat(self) -> bool:
        """포지션 없음 여부"""
        return self.qty == Decimal("0") or self.side is None
    
    @property
    def is_long(self) -> bool:
        """롱 포지션 여부"""
        return self.side == "LONG" and self.qty > 0
    
    @property
    def is_short(self) -> bool:
        """숏 포지션 여부"""
        return self.side == "SHORT" and self.qty > 0


@dataclass(frozen=True)
class Balance:
    """잔고 정보 (읽기 전용)"""
    asset: str
    free: Decimal
    locked: Decimal
    
    @property
    def total(self) -> Decimal:
        return self.free + self.locked


@dataclass(frozen=True)
class OpenOrder:
    """오픈 주문 정보 (읽기 전용)"""
    exchange_order_id: str
    client_order_id: str | None
    symbol: str
    side: str
    order_type: str
    original_qty: Decimal
    executed_qty: Decimal
    price: Decimal | None
    stop_price: Decimal | None
    status: str


@dataclass(frozen=True)
class TradeEvent:
    """체결 이벤트 (읽기 전용)
    
    WebSocket ORDER_TRADE_UPDATE에서 체결 발생 시 생성.
    on_trade() 콜백에서 사용.
    
    Attributes:
        trade_id: 거래소 체결 ID
        order_id: 거래소 주문 ID
        client_order_id: 클라이언트 주문 ID (AlphaEngine 주문인 경우 ae-xxx)
        symbol: 거래 심볼
        side: 체결 방향 (BUY, SELL)
        price: 체결 가격
        quantity: 체결 수량
        realized_pnl: 실현 손익 (청산 체결 시)
        commission: 수수료
        commission_asset: 수수료 자산 (USDT 등)
        timestamp: 체결 시간 (UTC)
    """
    trade_id: str
    order_id: str
    client_order_id: str | None
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    realized_pnl: Decimal
    commission: Decimal
    commission_asset: str
    timestamp: datetime
    
    @property
    def is_buy(self) -> bool:
        """매수 체결 여부"""
        return self.side == "BUY"
    
    @property
    def is_sell(self) -> bool:
        """매도 체결 여부"""
        return self.side == "SELL"
    
    @property
    def is_reduce(self) -> bool:
        """청산 체결 여부 (포지션 축소)
        
        realized_pnl이 0이 아니면 청산 체결.
        """
        return self.realized_pnl != Decimal("0")
    
    @property
    def is_profitable(self) -> bool:
        """이익 실현 여부"""
        return self.realized_pnl > Decimal("0")
    
    @property
    def is_alphaengine_order(self) -> bool:
        """AlphaEngine 발행 주문 여부"""
        return self.client_order_id is not None and self.client_order_id.startswith("ae-")


@dataclass(frozen=True)
class OrderEvent:
    """주문 상태 변경 이벤트 (읽기 전용)
    
    WebSocket ORDER_TRADE_UPDATE에서 주문 상태 변경 시 생성.
    on_order_update() 콜백에서 사용.
    
    Attributes:
        order_id: 거래소 주문 ID
        client_order_id: 클라이언트 주문 ID
        symbol: 거래 심볼
        status: 주문 상태 (NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED)
        order_type: 주문 유형 (LIMIT, MARKET, STOP_MARKET, TAKE_PROFIT_MARKET 등)
        side: 주문 방향 (BUY, SELL)
        price: 주문 가격 (LIMIT 주문)
        stop_price: 트리거 가격 (STOP 주문)
        original_qty: 원래 수량
        executed_qty: 체결된 수량
        avg_price: 평균 체결 가격
        reduce_only: 청산 전용 주문 여부
        close_position: 포지션 전체 청산 주문 여부
        timestamp: 이벤트 시간 (UTC)
    """
    order_id: str
    client_order_id: str | None
    symbol: str
    status: str
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
    
    @property
    def is_new(self) -> bool:
        """신규 주문 여부"""
        return self.status == "NEW"
    
    @property
    def is_filled(self) -> bool:
        """완전 체결 여부"""
        return self.status == "FILLED"
    
    @property
    def is_partially_filled(self) -> bool:
        """부분 체결 여부"""
        return self.status == "PARTIALLY_FILLED"
    
    @property
    def is_canceled(self) -> bool:
        """취소 여부"""
        return self.status == "CANCELED"
    
    @property
    def is_rejected(self) -> bool:
        """거부 여부"""
        return self.status == "REJECTED"
    
    @property
    def is_expired(self) -> bool:
        """만료 여부"""
        return self.status == "EXPIRED"
    
    @property
    def is_active(self) -> bool:
        """활성 주문 여부 (NEW 또는 PARTIALLY_FILLED)"""
        return self.status in ("NEW", "PARTIALLY_FILLED")
    
    @property
    def is_stop_order(self) -> bool:
        """스탑 주문 여부 (손절/익절)"""
        return self.order_type in ("STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET")
    
    @property
    def is_stop_loss(self) -> bool:
        """손절 주문 여부"""
        return self.order_type in ("STOP", "STOP_MARKET")
    
    @property
    def is_take_profit(self) -> bool:
        """익절 주문 여부"""
        return self.order_type in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET")
    
    @property
    def remaining_qty(self) -> Decimal:
        """미체결 수량"""
        return self.original_qty - self.executed_qty
    
    @property
    def is_alphaengine_order(self) -> bool:
        """AlphaEngine 발행 주문 여부"""
        return self.client_order_id is not None and self.client_order_id.startswith("ae-")


class MarketDataProvider(Protocol):
    """시장 데이터 제공자 Protocol
    
    전략에서 multi-timeframe 데이터를 조회하기 위한 인터페이스.
    """
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """OHLCV DataFrame 조회
        
        Args:
            symbol: 거래 심볼 (예: XRPUSDT)
            timeframe: 시간 간격 (1m, 5m, 15m, 1h, 4h, 1d 등)
            limit: 조회 개수
            
        Returns:
            DataFrame with DatetimeIndex 'time' and columns: open, high, low, close, volume
        """
        ...
    
    async def get_bars(
        self,
        symbol: str,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """캔들스틱(Bar) 데이터 조회 (레거시, get_ohlcv 권장)
        
        Args:
            symbol: 거래 심볼 (예: XRPUSDT)
            timeframe: 시간 간격 (1m, 5m, 15m, 1h, 4h, 1d 등)
            limit: 조회 개수
            
        Returns:
            Bar 데이터 리스트 (오래된 것부터 최신 순)
        """
        ...
    
    async def get_current_price(self, symbol: str) -> Decimal | None:
        """현재가 조회"""
        ...


def _empty_ohlcv() -> pd.DataFrame:
    """빈 OHLCV DataFrame 생성"""
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


@dataclass
class StrategyTickContext:
    """전략 실행 컨텍스트
    
    전략의 on_tick()에 전달되는 모든 정보.
    전략은 이 컨텍스트만으로 의사결정해야 함.
    
    Attributes:
        scope: 거래 범위 (거래소, 장소, 계좌, 심볼, 모드)
        now: 현재 시간 (UTC)
        position: 현재 포지션 (없으면 None)
        balances: 자산별 잔고 딕셔너리
        open_orders: 오픈 주문 목록
        ohlcv: OHLCV DataFrame (index=DatetimeIndex 'time', columns=open,high,low,close,volume)
        bars: 최근 캔들스틱 목록 - 레거시 호환 (최신이 마지막)
        current_price: 현재 가격 (마지막 종가)
        strategy_state: 전략별 상태 저장소 (on_tick 간 유지)
        engine_mode: 엔진 모드 (RUNNING, PAUSED, SAFE)
        market_data: 시장 데이터 제공자 (multi-timeframe 조회용)
        risk_config: 리스크/리워드 설정 (config_store의 "risk" 키)
    """
    scope: Scope
    now: datetime
    position: Position | None
    balances: dict[str, Balance]
    open_orders: list[OpenOrder]
    ohlcv: pd.DataFrame
    bars: list[Bar]
    current_price: Decimal | None
    strategy_state: dict[str, Any]
    engine_mode: str
    market_data: MarketDataProvider | None = None
    risk_config: dict[str, Any] | None = None
    
    @property
    def symbol(self) -> str | None:
        """심볼"""
        return self.scope.symbol
    
    @property
    def usdt_balance(self) -> Balance | None:
        """USDT 잔고"""
        return self.balances.get("USDT")
    
    @property
    def has_position(self) -> bool:
        """포지션 보유 여부"""
        return self.position is not None and not self.position.is_flat
    
    @property
    def has_open_orders(self) -> bool:
        """오픈 주문 존재 여부"""
        return len(self.open_orders) > 0
    
    @property
    def can_trade(self) -> bool:
        """거래 가능 여부 (RUNNING 모드)"""
        return self.engine_mode == "RUNNING"
    
    @property
    def close_only(self) -> bool:
        """청산만 가능 여부 (SAFE 모드)"""
        return self.engine_mode == "SAFE"
    
    @property
    def risk_per_trade(self) -> Decimal:
        """거래당 리스크 비율 (기본 2%)
        
        ConfigStore의 "risk.risk_per_trade" 값을 반환.
        손절 방식과 무관하게 수량 계산에 사용.
        """
        if self.risk_config:
            return Decimal(str(self.risk_config.get("risk_per_trade", "0.02")))
        return Decimal("0.02")
    
    @property
    def reward_ratio(self) -> Decimal:
        """R:R 비율 (기본 1.5)
        
        ConfigStore의 "risk.reward_ratio" 값을 반환.
        익절가 = 진입가 ± (손절거리 × reward_ratio)
        """
        if self.risk_config:
            return Decimal(str(self.risk_config.get("reward_ratio", "1.5")))
        return Decimal("1.5")
    
    @property
    def partial_tp_ratio(self) -> Decimal:
        """부분 익절 비율 (기본 50%)
        
        ConfigStore의 "risk.partial_tp_ratio" 값을 반환.
        부분 익절 수량 = 전체 수량 × partial_tp_ratio
        """
        if self.risk_config:
            return Decimal(str(self.risk_config.get("partial_tp_ratio", "0.5")))
        return Decimal("0.5")
    
    @property
    def equity_reset_trades(self) -> int:
        """자산 재평가 주기 (기본 50거래)
        
        ConfigStore의 "risk.equity_reset_trades" 값을 반환.
        이 거래 수마다 account_equity를 현재 잔고로 재설정.
        """
        if self.risk_config:
            return int(self.risk_config.get("equity_reset_trades", 50))
        return 50
    
    async def get_ohlcv(
        self,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        """다른 timeframe의 OHLCV 데이터 조회 (Multi-Timeframe 지원)
        
        Args:
            timeframe: 시간 간격 (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            limit: 조회 개수 (기본 100)
            
        Returns:
            OHLCV DataFrame (index=DatetimeIndex 'time', columns=open,high,low,close,volume)
            
        사용 예시:
        ```python
        # 15분봉 조회
        ohlcv_15m = await ctx.get_ohlcv("15m", limit=50)
        
        # 1시간봉 조회
        ohlcv_1h = await ctx.get_ohlcv("1h", limit=24)
        
        # 최신 종가
        close_price = ohlcv_15m["close"].iloc[-1]
        ```
        """
        if not self.market_data or not self.symbol:
            return _empty_ohlcv()
        
        try:
            return await self.market_data.get_ohlcv(
                symbol=self.symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except Exception:
            return _empty_ohlcv()
    
    async def get_bars(
        self,
        timeframe: str,
        limit: int = 100,
    ) -> list[Bar]:
        """다른 timeframe의 캔들 데이터 조회 (레거시 호환, get_ohlcv 권장)
        
        Args:
            timeframe: 시간 간격 (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            limit: 조회 개수 (기본 100)
            
        Returns:
            Bar 리스트 (오래된 것부터 최신 순)
        """
        if not self.market_data or not self.symbol:
            return []
        
        try:
            bars_data = await self.market_data.get_bars(
                symbol=self.symbol,
                timeframe=timeframe,
                limit=limit,
            )
            
            bars = []
            for bd in bars_data:
                ts = bd.get("ts")
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                
                bars.append(Bar(
                    ts=ts,
                    open=Decimal(str(bd.get("open", "0"))),
                    high=Decimal(str(bd.get("high", "0"))),
                    low=Decimal(str(bd.get("low", "0"))),
                    close=Decimal(str(bd.get("close", "0"))),
                    volume=Decimal(str(bd.get("volume", "0"))),
                ))
            
            return bars
            
        except Exception:
            return []


class CommandEmitter(Protocol):
    """Command 발행 프로토콜
    
    전략에서 Command를 발행하기 위한 인터페이스.
    실제 구현은 StrategyRunner에서 제공.
    """
    
    async def place_order(
        self,
        side: str,
        order_type: str,
        quantity: str | Decimal,
        price: str | Decimal | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        position_side: str = "BOTH",
    ) -> str:
        """주문 발행
        
        Args:
            side: BUY 또는 SELL
            order_type: LIMIT, MARKET, STOP_MARKET 등
            quantity: 수량
            price: 가격 (LIMIT 주문 시)
            time_in_force: GTC, IOC, FOK
            reduce_only: 청산 전용 여부
            position_side: LONG, SHORT, BOTH
            
        Returns:
            command_id
        """
        ...
    
    async def cancel_order(
        self,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> str:
        """주문 취소
        
        Args:
            exchange_order_id: 거래소 주문 ID
            client_order_id: 클라이언트 주문 ID
            
        Returns:
            command_id
        """
        ...
    
    async def close_position(self, reduce_only: bool = True) -> str:
        """포지션 청산
        
        현재 포지션을 시장가로 청산.
        
        Returns:
            command_id
        """
        ...
    
    async def cancel_all_orders(self) -> str:
        """모든 오픈 주문 취소
        
        Returns:
            command_id
        """
        ...


class Strategy(ABC):
    """전략 추상 클래스
    
    모든 전략은 이 클래스를 상속하여 구현.
    
    구현 규칙:
    1. on_tick()에서 거래소 API 직접 호출 금지
    2. emit을 통해서만 Command 발행
    3. strategy_state를 통해 상태 유지 (ctx.strategy_state)
    4. 예외 발생 시 전략 실행 중단되므로 적절한 예외 처리 필요
    
    사용 예시:
    ```python
    class MyStrategy(Strategy):
        @property
        def name(self) -> str:
            return "MyStrategy"
        
        @property
        def version(self) -> str:
            return "1.0.0"
        
        async def on_tick(self, ctx: StrategyTickContext, emit: CommandEmitter) -> None:
            if ctx.can_trade and not ctx.has_position:
                if self._should_enter(ctx):
                    await emit.place_order(
                        side="BUY",
                        order_type="MARKET",
                        quantity="10",
                    )
    ```
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """전략 이름"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """전략 버전"""
        pass
    
    @property
    def description(self) -> str:
        """전략 설명"""
        return ""
    
    @property
    def default_params(self) -> dict[str, Any]:
        """기본 파라미터
        
        전략 설정에서 오버라이드 가능한 기본 파라미터.
        """
        return {}
    
    async def on_init(self, params: dict[str, Any]) -> None:
        """초기화 콜백
        
        전략 로드 시 한 번 호출.
        파라미터 검증 및 초기 설정 수행.
        
        Args:
            params: 설정에서 전달된 파라미터 (default_params 오버라이드)
        """
        pass
    
    async def on_start(self, ctx: StrategyTickContext) -> None:
        """시작 콜백
        
        전략 실행 시작 시 한 번 호출.
        초기 상태 설정 가능.
        
        Args:
            ctx: 현재 컨텍스트
        """
        pass
    
    @abstractmethod
    async def on_tick(
        self,
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """틱 콜백 (필수 구현)
        
        매 틱마다 호출되는 메인 전략 로직.
        
        Args:
            ctx: 현재 컨텍스트 (읽기 전용)
            emit: Command 발행기
        """
        pass
    
    async def on_stop(self, ctx: StrategyTickContext) -> None:
        """종료 콜백
        
        전략 실행 종료 시 호출.
        정리 작업 수행 가능.
        
        Args:
            ctx: 현재 컨텍스트
        """
        pass
    
    async def on_error(self, error: Exception, ctx: StrategyTickContext) -> bool:
        """에러 콜백
        
        전략 실행 중 에러 발생 시 호출.
        
        Args:
            error: 발생한 예외
            ctx: 현재 컨텍스트
            
        Returns:
            True: 에러 복구 후 계속 실행
            False: 전략 중단
        """
        return False  # 기본: 중단
    
    # =========================================================================
    # 이벤트 기반 콜백 (선택적 구현)
    # 
    # 아래 콜백들은 WebSocket을 통해 실시간으로 호출됩니다.
    # 구현하지 않으면 호출되지 않습니다 (기본 구현은 아무 작업도 하지 않음).
    # 
    # 사용 시나리오:
    # - 부분 익절 후 즉시 손절 조정
    # - 체결 알림 발송
    # - 주문 거부 시 재시도
    # - 손절 체결 시 정리 작업
    # =========================================================================
    
    async def on_trade(
        self,
        trade: "TradeEvent",
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """체결 이벤트 콜백 (선택적 구현)
        
        WebSocket을 통해 체결 발생 시 **즉시** 호출.
        on_tick()과 달리 틱 간격 없이 실시간으로 반응 가능.
        
        Args:
            trade: 체결 정보 (TradeEvent)
            ctx: 현재 컨텍스트 (실시간 갱신)
            emit: Command 발행기
        
        사용 예시:
        ```python
        async def on_trade(
            self,
            trade: TradeEvent,
            ctx: StrategyTickContext,
            emit: CommandEmitter,
        ) -> None:
            # 부분 익절 감지 → 손절을 진입가로 이동
            if trade.is_reduce and trade.is_profitable:
                state = ctx.strategy_state
                if not state.get("partial_tp_done"):
                    state["partial_tp_done"] = True
                    
                    # 기존 손절 취소
                    for order in ctx.open_orders:
                        if order.order_type == "STOP_MARKET":
                            await emit.cancel_order(
                                exchange_order_id=order.exchange_order_id
                            )
                    
                    # 새 손절 (진입가)
                    entry = state.get("entry_price")
                    if ctx.position and entry:
                        await emit.place_order(
                            side="SELL",
                            order_type="STOP_MARKET",
                            quantity=str(ctx.position.qty),
                            stop_price=str(entry),
                            reduce_only=True,
                        )
        ```
        
        주의:
        - on_tick()과 동일한 strategy_state를 공유합니다.
        - 중복 처리 방지를 위해 플래그 사용을 권장합니다.
        - 예외 발생 시 on_error()가 호출됩니다.
        """
        pass  # 기본: 아무 작업 안 함
    
    async def on_order_update(
        self,
        order: "OrderEvent",
        ctx: StrategyTickContext,
        emit: CommandEmitter,
    ) -> None:
        """주문 상태 변경 콜백 (선택적 구현)
        
        WebSocket을 통해 주문 상태 변경 시 **즉시** 호출.
        NEW, FILLED, CANCELED, REJECTED, EXPIRED 등 모든 상태 변경에 대해 호출.
        
        Args:
            order: 주문 정보 (OrderEvent)
            ctx: 현재 컨텍스트 (실시간 갱신)
            emit: Command 발행기
        
        사용 예시:
        ```python
        async def on_order_update(
            self,
            order: OrderEvent,
            ctx: StrategyTickContext,
            emit: CommandEmitter,
        ) -> None:
            # 손절 체결 시 상태 초기화
            if order.is_filled and order.is_stop_loss:
                ctx.strategy_state.clear()
                logger.info(f"Stop loss hit at {order.avg_price}")
            
            # 주문 거부 시 로깅
            elif order.is_rejected:
                logger.error(f"Order rejected: {order.order_id}")
            
            # 익절 주문 체결 시 후속 작업
            elif order.is_filled and order.is_take_profit:
                logger.info(f"Take profit hit at {order.avg_price}")
        ```
        
        주의:
        - 체결(FILLED)과 on_trade()는 별개입니다. on_trade()는 실제 체결 데이터,
          on_order_update()는 주문 상태 변경입니다.
        - 동일 체결에 대해 두 콜백이 모두 호출될 수 있습니다.
        """
        pass  # 기본: 아무 작업 안 함
