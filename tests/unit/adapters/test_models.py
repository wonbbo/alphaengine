"""
공통 모델 테스트

Balance, Position, Order, Trade, OrderRequest 모델 테스트.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from adapters.models import Balance, Position, Order, Trade, OrderRequest
from core.types import OrderSide, OrderType, OrderStatus, PositionSide, TimeInForce


class TestBalance:
    """Balance 모델 테스트"""
    
    def test_create_balance(self) -> None:
        """잔고 생성"""
        balance = Balance(
            asset="USDT",
            wallet_balance=Decimal("10000"),
            available_balance=Decimal("9500"),
        )
        
        assert balance.asset == "USDT"
        assert balance.wallet_balance == Decimal("10000")
        assert balance.available_balance == Decimal("9500")
    
    def test_total_property(self) -> None:
        """총 잔고 계산"""
        balance = Balance(
            asset="USDT",
            wallet_balance=Decimal("10000"),
            available_balance=Decimal("9500"),
            unrealized_pnl=Decimal("100"),
        )
        
        assert balance.total == Decimal("10100")
    
    def test_balance_is_frozen(self) -> None:
        """불변 객체 확인"""
        balance = Balance(
            asset="USDT",
            wallet_balance=Decimal("10000"),
            available_balance=Decimal("9500"),
        )
        
        with pytest.raises(Exception):
            balance.wallet_balance = Decimal("5000")  # type: ignore


class TestPosition:
    """Position 모델 테스트"""
    
    def test_create_position(self) -> None:
        """포지션 생성"""
        position = Position(
            symbol="XRPUSDT",
            side=PositionSide.LONG.value,
            quantity=Decimal("1000"),
            entry_price=Decimal("0.5000"),
        )
        
        assert position.symbol == "XRPUSDT"
        assert position.side == "LONG"
        assert position.quantity == Decimal("1000")
    
    def test_is_long_property(self) -> None:
        """롱 포지션 확인"""
        long_pos = Position(
            symbol="XRPUSDT",
            side=PositionSide.LONG.value,
            quantity=Decimal("100"),
            entry_price=Decimal("0.5"),
        )
        
        assert long_pos.is_long is True
        assert long_pos.is_short is False
    
    def test_is_short_property(self) -> None:
        """숏 포지션 확인"""
        short_pos = Position(
            symbol="XRPUSDT",
            side=PositionSide.SHORT.value,
            quantity=Decimal("100"),
            entry_price=Decimal("0.5"),
        )
        
        assert short_pos.is_short is True
        assert short_pos.is_long is False
    
    def test_notional_property(self) -> None:
        """명목 가치 계산"""
        position = Position(
            symbol="XRPUSDT",
            side=PositionSide.LONG.value,
            quantity=Decimal("1000"),
            entry_price=Decimal("0.5"),
        )
        
        assert position.notional == Decimal("500")


class TestOrder:
    """Order 모델 테스트"""
    
    def test_create_order(self) -> None:
        """주문 생성"""
        order = Order(
            order_id="12345",
            client_order_id="ae-test-001",
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            order_type=OrderType.MARKET.value,
            status=OrderStatus.NEW.value,
            original_qty=Decimal("100"),
        )
        
        assert order.order_id == "12345"
        assert order.client_order_id == "ae-test-001"
    
    def test_remaining_qty_property(self) -> None:
        """잔여 수량 계산"""
        order = Order(
            order_id="12345",
            client_order_id="ae-test-001",
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            order_type=OrderType.MARKET.value,
            status=OrderStatus.PARTIALLY_FILLED.value,
            original_qty=Decimal("100"),
            executed_qty=Decimal("30"),
        )
        
        assert order.remaining_qty == Decimal("70")
    
    def test_is_filled_property(self) -> None:
        """체결 완료 확인"""
        filled_order = Order(
            order_id="12345",
            client_order_id="ae-test-001",
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            order_type=OrderType.MARKET.value,
            status=OrderStatus.FILLED.value,
            original_qty=Decimal("100"),
            executed_qty=Decimal("100"),
        )
        
        assert filled_order.is_filled is True
        assert filled_order.is_open is False
    
    def test_is_open_property(self) -> None:
        """오픈 주문 확인"""
        new_order = Order(
            order_id="12345",
            client_order_id="ae-test-001",
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            order_type=OrderType.LIMIT.value,
            status=OrderStatus.NEW.value,
            original_qty=Decimal("100"),
        )
        
        assert new_order.is_open is True
        
        partial_order = Order(
            order_id="12346",
            client_order_id="ae-test-002",
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            order_type=OrderType.LIMIT.value,
            status=OrderStatus.PARTIALLY_FILLED.value,
            original_qty=Decimal("100"),
            executed_qty=Decimal("50"),
        )
        
        assert partial_order.is_open is True


class TestOrderRequest:
    """OrderRequest 모델 테스트"""
    
    def test_create_market_order(self) -> None:
        """시장가 주문 생성"""
        request = OrderRequest.market(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            client_order_id="ae-test-001",
        )
        
        assert request.symbol == "XRPUSDT"
        assert request.side == "BUY"
        assert request.order_type == "MARKET"
        assert request.quantity == Decimal("100")
    
    def test_create_limit_order(self) -> None:
        """지정가 주문 생성"""
        request = OrderRequest.limit(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            price=Decimal("0.5"),
        )
        
        assert request.order_type == "LIMIT"
        assert request.price == Decimal("0.5")
    
    def test_create_stop_market_order(self) -> None:
        """스탑 마켓 주문 생성"""
        request = OrderRequest.stop_market(
            symbol="XRPUSDT",
            side=OrderSide.SELL.value,
            quantity=Decimal("100"),
            stop_price=Decimal("0.4"),
        )
        
        assert request.order_type == "STOP_MARKET"
        assert request.stop_price == Decimal("0.4")
        assert request.reduce_only is True
    
    def test_validation_quantity_positive(self) -> None:
        """수량 양수 검증"""
        with pytest.raises(ValueError, match="quantity must be positive"):
            OrderRequest(
                symbol="XRPUSDT",
                side=OrderSide.BUY.value,
                order_type=OrderType.MARKET.value,
                quantity=Decimal("0"),
            )
    
    def test_validation_limit_requires_price(self) -> None:
        """LIMIT 주문은 가격 필수"""
        with pytest.raises(ValueError, match="price is required"):
            OrderRequest(
                symbol="XRPUSDT",
                side=OrderSide.BUY.value,
                order_type=OrderType.LIMIT.value,
                quantity=Decimal("100"),
                price=None,
            )
    
    def test_validation_stop_requires_stop_price(self) -> None:
        """STOP 주문은 stop_price 필수"""
        with pytest.raises(ValueError, match="stop_price is required"):
            OrderRequest(
                symbol="XRPUSDT",
                side=OrderSide.SELL.value,
                order_type=OrderType.STOP_MARKET.value,
                quantity=Decimal("100"),
            )
    
    def test_to_dict(self) -> None:
        """딕셔너리 변환"""
        request = OrderRequest.limit(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            price=Decimal("0.5"),
            client_order_id="ae-test-001",
        )
        
        params = request.to_dict()
        
        assert params["symbol"] == "XRPUSDT"
        assert params["side"] == "BUY"
        assert params["type"] == "LIMIT"
        assert params["quantity"] == "100"
        assert params["price"] == "0.5"
        assert params["newClientOrderId"] == "ae-test-001"
        assert params["timeInForce"] == "GTC"


class TestTrade:
    """Trade 모델 테스트"""
    
    def test_create_trade(self) -> None:
        """체결 생성"""
        trade = Trade(
            trade_id="987654",
            order_id="12345",
            client_order_id="ae-test-001",
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            price=Decimal("0.5"),
            quote_qty=Decimal("50"),
            commission=Decimal("0.02"),
            commission_asset="USDT",
        )
        
        assert trade.trade_id == "987654"
        assert trade.order_id == "12345"
        assert trade.quantity == Decimal("100")
        assert trade.price == Decimal("0.5")
