"""
Binance 모델 변환 테스트

Binance API 응답 -> 공통 모델 변환 테스트.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from adapters.binance.models import (
    parse_balance,
    parse_position,
    parse_order,
    parse_trade,
    is_zero_position,
    is_zero_balance,
)
from adapters.models import Balance, Position, Order, Trade


class TestParseBalance:
    """parse_balance 테스트"""
    
    def test_parse_balance(self, binance_balance_response: dict) -> None:
        """잔고 파싱"""
        balance = parse_balance(binance_balance_response)
        
        assert isinstance(balance, Balance)
        assert balance.asset == "USDT"
        assert balance.wallet_balance == Decimal("10000.50000000")
        assert balance.available_balance == Decimal("9500.25000000")
    
    def test_uses_decimal_not_float(self, binance_balance_response: dict) -> None:
        """Decimal 타입 확인"""
        balance = parse_balance(binance_balance_response)
        
        assert isinstance(balance.wallet_balance, Decimal)
        assert isinstance(balance.available_balance, Decimal)
        assert isinstance(balance.unrealized_pnl, Decimal)
    
    def test_parse_balance_with_pnl(self, binance_balance_response: dict) -> None:
        """미실현 손익 포함 파싱"""
        balance = parse_balance(binance_balance_response)
        
        assert balance.unrealized_pnl == Decimal("123.45000000")


class TestParsePosition:
    """parse_position 테스트"""
    
    def test_parse_position(self, binance_position_response: dict) -> None:
        """포지션 파싱"""
        position = parse_position(binance_position_response)
        
        assert isinstance(position, Position)
        assert position.symbol == "XRPUSDT"
        assert position.side == "LONG"
        assert position.quantity == Decimal("1000")
        assert position.entry_price == Decimal("0.5123")
    
    def test_uses_decimal_not_float(self, binance_position_response: dict) -> None:
        """Decimal 타입 확인"""
        position = parse_position(binance_position_response)
        
        assert isinstance(position.quantity, Decimal)
        assert isinstance(position.entry_price, Decimal)
        assert isinstance(position.unrealized_pnl, Decimal)
    
    def test_parse_position_negative_qty_is_short(self) -> None:
        """음수 수량은 SHORT"""
        response = {
            "symbol": "XRPUSDT",
            "positionAmt": "-500",
            "entryPrice": "0.6000",
            "unRealizedProfit": "-10.00",
            "leverage": "5",
            "marginType": "cross",
            "positionSide": "BOTH",
        }
        
        position = parse_position(response)
        
        assert position.side == "SHORT"
        assert position.quantity == Decimal("500")  # 절대값
    
    def test_parse_position_extracts_leverage(self, binance_position_response: dict) -> None:
        """레버리지 추출"""
        position = parse_position(binance_position_response)
        
        assert position.leverage == 10
    
    def test_liquidation_price_zero_is_none(self) -> None:
        """청산가 0은 None"""
        response = {
            "symbol": "XRPUSDT",
            "positionAmt": "100",
            "entryPrice": "0.5000",
            "liquidationPrice": "0",
            "positionSide": "LONG",
        }
        
        position = parse_position(response)
        
        assert position.liquidation_price is None


class TestParseOrder:
    """parse_order 테스트"""
    
    def test_parse_order(self, binance_order_response: dict) -> None:
        """주문 파싱"""
        order = parse_order(binance_order_response)
        
        assert isinstance(order, Order)
        assert order.order_id == "12345678"
        assert order.client_order_id == "ae-test-order-001"
        assert order.symbol == "XRPUSDT"
        assert order.side == "BUY"
        assert order.order_type == "LIMIT"
        assert order.status == "NEW"
    
    def test_uses_decimal_not_float(self, binance_order_response: dict) -> None:
        """Decimal 타입 확인"""
        order = parse_order(binance_order_response)
        
        assert isinstance(order.original_qty, Decimal)
        assert isinstance(order.executed_qty, Decimal)
    
    def test_parse_order_price_zero_is_none(self) -> None:
        """가격 0은 None"""
        response = {
            "orderId": 12345,
            "symbol": "XRPUSDT",
            "status": "NEW",
            "clientOrderId": "ae-test",
            "price": "0",
            "avgPrice": "0",
            "origQty": "100",
            "executedQty": "0",
            "side": "BUY",
            "type": "MARKET",
        }
        
        order = parse_order(response)
        
        assert order.price is None
        assert order.avg_price is None
    
    def test_parse_order_with_timestamp(self, binance_order_response: dict) -> None:
        """타임스탬프 변환"""
        order = parse_order(binance_order_response)
        
        assert order.created_at is not None
        assert isinstance(order.created_at, datetime)
        assert order.created_at.tzinfo == timezone.utc


class TestParseTrade:
    """parse_trade 테스트"""
    
    def test_parse_trade_from_rest(self, binance_trade_response: dict) -> None:
        """REST API 응답에서 체결 파싱"""
        trade = parse_trade(binance_trade_response)
        
        assert isinstance(trade, Trade)
        assert trade.trade_id == "987654321"
        assert trade.order_id == "12345678"
        assert trade.symbol == "XRPUSDT"
        assert trade.side == "BUY"
        assert trade.quantity == Decimal("100")
        assert trade.price == Decimal("0.5123")
    
    def test_parse_trade_from_websocket(self) -> None:
        """WebSocket 응답에서 체결 파싱"""
        ws_response = {
            "t": 987654321,  # trade_id
            "i": 12345678,   # order_id
            "c": "ae-test",  # client_order_id
            "s": "XRPUSDT",  # symbol
            "S": "BUY",      # side
            "L": "0.5123",   # last price
            "l": "100",      # last qty
            "n": "0.02049",  # commission
            "N": "USDT",     # commission asset
            "T": 1568879465651,  # trade time
            "rp": "0",       # realized pnl
            "m": False,      # is maker
        }
        
        trade = parse_trade(ws_response)
        
        assert trade.trade_id == "987654321"
        assert trade.order_id == "12345678"
        assert trade.client_order_id == "ae-test"
        assert trade.quantity == Decimal("100")
    
    def test_uses_decimal_not_float(self, binance_trade_response: dict) -> None:
        """Decimal 타입 확인"""
        trade = parse_trade(binance_trade_response)
        
        assert isinstance(trade.quantity, Decimal)
        assert isinstance(trade.price, Decimal)
        assert isinstance(trade.commission, Decimal)


class TestIsZeroPosition:
    """is_zero_position 테스트"""
    
    def test_zero_position(self) -> None:
        """0 포지션 감지"""
        response = {"positionAmt": "0"}
        assert is_zero_position(response) is True
    
    def test_non_zero_position(self) -> None:
        """0이 아닌 포지션"""
        response = {"positionAmt": "100"}
        assert is_zero_position(response) is False
        
        response = {"positionAmt": "-50"}
        assert is_zero_position(response) is False
    
    def test_missing_field(self) -> None:
        """필드 없음"""
        response = {}
        assert is_zero_position(response) is True


class TestIsZeroBalance:
    """is_zero_balance 테스트"""
    
    def test_zero_balance(self) -> None:
        """0 잔고 감지"""
        response = {"balance": "0"}
        assert is_zero_balance(response) is True
    
    def test_non_zero_balance(self) -> None:
        """0이 아닌 잔고"""
        response = {"balance": "100.50"}
        assert is_zero_balance(response) is False
