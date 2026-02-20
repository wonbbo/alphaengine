"""
어댑터 공통 데이터 모델

거래소 API 응답을 표준화한 도메인 모델.
모든 금액/수량은 Decimal 타입 사용.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from core.types import OrderSide, OrderType, OrderStatus, PositionSide, TimeInForce


@dataclass(frozen=True)
class Balance:
    """잔고 정보
    
    Attributes:
        asset: 자산 코드 (예: USDT, BTC)
        wallet_balance: 지갑 잔고
        available_balance: 사용 가능 잔고
        cross_wallet_balance: Cross 지갑 잔고 (Futures)
        unrealized_pnl: 미실현 손익
    """
    
    asset: str
    wallet_balance: Decimal
    available_balance: Decimal
    cross_wallet_balance: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    
    @property
    def total(self) -> Decimal:
        """총 잔고 (지갑 + 미실현 손익)"""
        return self.wallet_balance + self.unrealized_pnl


@dataclass(frozen=True)
class Position:
    """포지션 정보
    
    Attributes:
        symbol: 거래 심볼
        side: 포지션 방향 (LONG/SHORT/BOTH)
        quantity: 포지션 수량 (절대값)
        entry_price: 평균 진입가
        unrealized_pnl: 미실현 손익
        leverage: 레버리지
        margin_type: 마진 타입 (ISOLATED/CROSS)
        liquidation_price: 청산가
        mark_price: 마크 가격
    """
    
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    leverage: int = 1
    margin_type: str = "CROSS"
    liquidation_price: Decimal | None = None
    mark_price: Decimal | None = None
    
    @property
    def is_long(self) -> bool:
        """롱 포지션 여부"""
        return self.side == PositionSide.LONG.value
    
    @property
    def is_short(self) -> bool:
        """숏 포지션 여부"""
        return self.side == PositionSide.SHORT.value
    
    @property
    def notional(self) -> Decimal:
        """명목 가치 (수량 * 진입가)"""
        return self.quantity * self.entry_price


@dataclass(frozen=True)
class Order:
    """주문 정보
    
    Attributes:
        order_id: 거래소 주문 ID
        client_order_id: 클라이언트 주문 ID (ae-{command_id})
        symbol: 거래 심볼
        side: 주문 방향 (BUY/SELL)
        order_type: 주문 유형 (MARKET/LIMIT/STOP_MARKET 등)
        status: 주문 상태
        original_qty: 원래 주문 수량
        executed_qty: 체결된 수량
        price: 지정가 (LIMIT 주문)
        avg_price: 평균 체결가
        stop_price: 트리거 가격 (STOP 주문)
        time_in_force: 주문 유효 기간
        reduce_only: 포지션 축소 전용 여부
        created_at: 주문 생성 시간
        updated_at: 주문 업데이트 시간
    """
    
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    original_qty: Decimal
    executed_qty: Decimal = Decimal("0")
    price: Decimal | None = None
    avg_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = TimeInForce.GTC.value
    reduce_only: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    
    @property
    def remaining_qty(self) -> Decimal:
        """잔여 수량"""
        return self.original_qty - self.executed_qty
    
    @property
    def is_filled(self) -> bool:
        """완전 체결 여부"""
        return self.status == OrderStatus.FILLED.value
    
    @property
    def is_open(self) -> bool:
        """오픈 주문 여부 (NEW 또는 PARTIALLY_FILLED)"""
        return self.status in (
            OrderStatus.NEW.value,
            OrderStatus.PARTIALLY_FILLED.value,
        )
    
    @property
    def is_cancelled(self) -> bool:
        """취소 여부"""
        return self.status == OrderStatus.CANCELLED.value


@dataclass(frozen=True)
class Trade:
    """체결 정보
    
    Attributes:
        trade_id: 거래소 체결 ID
        order_id: 거래소 주문 ID
        client_order_id: 클라이언트 주문 ID
        symbol: 거래 심볼
        side: 체결 방향
        quantity: 체결 수량
        price: 체결 가격
        quote_qty: 체결 금액 (수량 * 가격)
        commission: 수수료
        commission_asset: 수수료 자산
        realized_pnl: 실현 손익
        is_maker: 메이커 여부
        trade_time: 체결 시간
    """
    
    trade_id: str
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    quote_qty: Decimal
    commission: Decimal = Decimal("0")
    commission_asset: str = "USDT"
    realized_pnl: Decimal = Decimal("0")
    is_maker: bool = False
    trade_time: datetime | None = None


@dataclass
class OrderRequest:
    """주문 요청
    
    place_order 메서드에 전달되는 주문 요청 정보.
    
    Attributes:
        symbol: 거래 심볼
        side: 주문 방향
        order_type: 주문 유형
        quantity: 주문 수량
        price: 지정가 (LIMIT 주문 필수)
        stop_price: 트리거 가격 (STOP 주문 필수)
        client_order_id: 클라이언트 주문 ID (선택)
        time_in_force: 주문 유효 기간
        reduce_only: 포지션 축소 전용 여부
        position_side: 포지션 방향 (Hedge Mode)
    """
    
    symbol: str
    side: str  # BUY / SELL
    order_type: str  # MARKET / LIMIT / STOP_MARKET 등
    quantity: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    client_order_id: str | None = None
    time_in_force: str = TimeInForce.GTC.value
    reduce_only: bool = False
    position_side: str | None = None  # LONG / SHORT (Hedge Mode)
    
    def __post_init__(self) -> None:
        """유효성 검증"""
        # 수량은 양수여야 함
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        
        # LIMIT 주문은 가격 필수
        if self.order_type == OrderType.LIMIT.value and self.price is None:
            raise ValueError("price is required for LIMIT orders")
        
        # STOP 주문은 stop_price 필수
        stop_types = (
            OrderType.STOP_MARKET.value,
            OrderType.TAKE_PROFIT_MARKET.value,
            OrderType.STOP.value,
            OrderType.TAKE_PROFIT.value,
        )
        if self.order_type in stop_types and self.stop_price is None:
            raise ValueError("stop_price is required for STOP orders")
    
    @classmethod
    def market(
        cls,
        symbol: str,
        side: str,
        quantity: Decimal,
        client_order_id: str | None = None,
        reduce_only: bool = False,
    ) -> "OrderRequest":
        """시장가 주문 생성"""
        return cls(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET.value,
            quantity=quantity,
            client_order_id=client_order_id,
            reduce_only=reduce_only,
        )
    
    @classmethod
    def limit(
        cls,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        client_order_id: str | None = None,
        time_in_force: str = TimeInForce.GTC.value,
        reduce_only: bool = False,
    ) -> "OrderRequest":
        """지정가 주문 생성"""
        return cls(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT.value,
            quantity=quantity,
            price=price,
            client_order_id=client_order_id,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
        )
    
    @classmethod
    def stop_market(
        cls,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        client_order_id: str | None = None,
        reduce_only: bool = True,
    ) -> "OrderRequest":
        """스탑 마켓 주문 생성 (손절)"""
        return cls(
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP_MARKET.value,
            quantity=quantity,
            stop_price=stop_price,
            client_order_id=client_order_id,
            reduce_only=reduce_only,
        )
    
    @classmethod
    def take_profit_market(
        cls,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        client_order_id: str | None = None,
        reduce_only: bool = True,
    ) -> "OrderRequest":
        """익절 마켓 주문 생성"""
        return cls(
            symbol=symbol,
            side=side,
            order_type=OrderType.TAKE_PROFIT_MARKET.value,
            quantity=quantity,
            stop_price=stop_price,
            client_order_id=client_order_id,
            reduce_only=reduce_only,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (API 요청용)"""
        result: dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "quantity": str(self.quantity),
        }
        
        if self.price is not None:
            result["price"] = str(self.price)
        
        if self.stop_price is not None:
            result["stopPrice"] = str(self.stop_price)
        
        if self.client_order_id is not None:
            result["newClientOrderId"] = self.client_order_id
        
        if self.order_type == OrderType.LIMIT.value:
            result["timeInForce"] = self.time_in_force
        
        if self.reduce_only:
            result["reduceOnly"] = "true"
        
        if self.position_side is not None:
            result["positionSide"] = self.position_side
        
        return result
