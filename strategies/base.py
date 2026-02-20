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
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

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
class StrategyTickContext:
    """전략 실행 컨텍스트 (읽기 전용)
    
    전략의 on_tick()에 전달되는 모든 정보.
    전략은 이 컨텍스트만으로 의사결정해야 함.
    
    Attributes:
        scope: 거래 범위 (거래소, 장소, 계좌, 심볼, 모드)
        now: 현재 시간 (UTC)
        position: 현재 포지션 (없으면 None)
        balances: 자산별 잔고 딕셔너리
        open_orders: 오픈 주문 목록
        bars: 최근 캔들스틱 목록 (최신이 마지막)
        current_price: 현재 가격 (마지막 종가)
        strategy_state: 전략별 상태 저장소 (on_tick 간 유지)
        engine_mode: 엔진 모드 (RUNNING, PAUSED, SAFE)
    """
    scope: Scope
    now: datetime
    position: Position | None
    balances: dict[str, Balance]
    open_orders: list[OpenOrder]
    bars: list[Bar]
    current_price: Decimal | None
    strategy_state: dict[str, Any]
    engine_mode: str
    
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
