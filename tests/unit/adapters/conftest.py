"""
어댑터 테스트 픽스처

공통 테스트 설정 및 픽스처 제공.
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from adapters.models import Balance, Position, Order, Trade, OrderRequest
from adapters.mock.exchange_client import MockExchangeRestClient, MockExchangeWsClient
from adapters.mock.notifier import MockNotifier
from core.types import OrderSide, OrderType, OrderStatus, PositionSide


# -------------------------------------------------------------------------
# 공통 데이터 픽스처
# -------------------------------------------------------------------------

@pytest.fixture
def sample_balance() -> Balance:
    """샘플 잔고"""
    return Balance(
        asset="USDT",
        wallet_balance=Decimal("10000.50"),
        available_balance=Decimal("9500.25"),
        cross_wallet_balance=Decimal("10000.50"),
        unrealized_pnl=Decimal("123.45"),
    )


@pytest.fixture
def sample_position() -> Position:
    """샘플 포지션"""
    return Position(
        symbol="XRPUSDT",
        side=PositionSide.LONG.value,
        quantity=Decimal("1000"),
        entry_price=Decimal("0.5123"),
        unrealized_pnl=Decimal("50.00"),
        leverage=10,
        margin_type="CROSS",
        liquidation_price=Decimal("0.2500"),
        mark_price=Decimal("0.5623"),
    )


@pytest.fixture
def sample_order() -> Order:
    """샘플 주문"""
    return Order(
        order_id="12345678",
        client_order_id="ae-test-order-001",
        symbol="XRPUSDT",
        side=OrderSide.BUY.value,
        order_type=OrderType.LIMIT.value,
        status=OrderStatus.NEW.value,
        original_qty=Decimal("100"),
        executed_qty=Decimal("0"),
        price=Decimal("0.5000"),
        time_in_force="GTC",
    )


@pytest.fixture
def sample_order_request() -> OrderRequest:
    """샘플 주문 요청"""
    return OrderRequest(
        symbol="XRPUSDT",
        side=OrderSide.BUY.value,
        order_type=OrderType.MARKET.value,
        quantity=Decimal("100"),
        client_order_id="ae-test-001",
    )


# -------------------------------------------------------------------------
# Mock 클라이언트 픽스처
# -------------------------------------------------------------------------

@pytest.fixture
def mock_rest_client() -> MockExchangeRestClient:
    """Mock REST 클라이언트"""
    return MockExchangeRestClient()


@pytest.fixture
def mock_notifier() -> MockNotifier:
    """Mock Notifier"""
    return MockNotifier()


# -------------------------------------------------------------------------
# Binance API 응답 샘플
# -------------------------------------------------------------------------

@pytest.fixture
def binance_balance_response() -> dict:
    """Binance 잔고 API 응답 샘플"""
    return {
        "accountAlias": "SgsR",
        "asset": "USDT",
        "balance": "10000.50000000",
        "crossWalletBalance": "10000.50000000",
        "crossUnPnl": "123.45000000",
        "availableBalance": "9500.25000000",
        "maxWithdrawAmount": "9500.25000000",
        "marginAvailable": True,
        "updateTime": 1617939110373,
    }


@pytest.fixture
def binance_position_response() -> dict:
    """Binance 포지션 API 응답 샘플"""
    return {
        "symbol": "XRPUSDT",
        "positionAmt": "1000",
        "entryPrice": "0.5123",
        "breakEvenPrice": "0.5125",
        "markPrice": "0.5623",
        "unRealizedProfit": "50.00",
        "liquidationPrice": "0.2500",
        "leverage": "10",
        "maxNotionalValue": "25000",
        "marginType": "cross",
        "isolatedMargin": "0.00000000",
        "isAutoAddMargin": "false",
        "positionSide": "LONG",
        "notional": "562.30",
        "isolatedWallet": "0",
        "updateTime": 1625474304765,
    }


@pytest.fixture
def binance_order_response() -> dict:
    """Binance 주문 API 응답 샘플"""
    return {
        "orderId": 12345678,
        "symbol": "XRPUSDT",
        "status": "NEW",
        "clientOrderId": "ae-test-order-001",
        "price": "0.5000",
        "avgPrice": "0.0000",
        "origQty": "100",
        "executedQty": "0",
        "cumQuote": "0",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "reduceOnly": False,
        "closePosition": False,
        "side": "BUY",
        "positionSide": "LONG",
        "stopPrice": "0.0000",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": False,
        "origType": "LIMIT",
        "time": 1568879465651,
        "updateTime": 1568879465651,
    }


@pytest.fixture
def binance_trade_response() -> dict:
    """Binance 체결 API 응답 샘플"""
    return {
        "symbol": "XRPUSDT",
        "id": 987654321,
        "orderId": 12345678,
        "side": "BUY",
        "price": "0.5123",
        "qty": "100",
        "realizedPnl": "0",
        "marginAsset": "USDT",
        "quoteQty": "51.23",
        "commission": "0.02049200",
        "commissionAsset": "USDT",
        "time": 1568879465651,
        "positionSide": "LONG",
        "maker": False,
        "buyer": True,
    }


@pytest.fixture
def binance_ws_account_update() -> dict:
    """Binance WebSocket ACCOUNT_UPDATE 메시지 샘플"""
    return {
        "e": "ACCOUNT_UPDATE",
        "T": 1564745798939,
        "E": 1564745798943,
        "a": {
            "m": "ORDER",
            "B": [
                {
                    "a": "USDT",
                    "wb": "10000.50000000",
                    "cw": "10000.50000000",
                    "bc": "50.00000000",
                }
            ],
            "P": [
                {
                    "s": "XRPUSDT",
                    "pa": "1000",
                    "ep": "0.5123",
                    "cr": "0",
                    "up": "50.00",
                    "mt": "cross",
                    "iw": "0.00000000",
                    "ps": "LONG",
                }
            ],
        },
    }


@pytest.fixture
def binance_ws_order_trade_update() -> dict:
    """Binance WebSocket ORDER_TRADE_UPDATE 메시지 샘플"""
    return {
        "e": "ORDER_TRADE_UPDATE",
        "T": 1568879465651,
        "E": 1568879465653,
        "o": {
            "s": "XRPUSDT",
            "c": "ae-test-order-001",
            "S": "BUY",
            "o": "MARKET",
            "f": "GTC",
            "q": "100",
            "p": "0",
            "ap": "0.5123",
            "sp": "0",
            "x": "TRADE",
            "X": "FILLED",
            "i": 12345678,
            "l": "100",
            "z": "100",
            "L": "0.5123",
            "n": "0.02049200",
            "N": "USDT",
            "T": 1568879465651,
            "t": 987654321,
            "b": "0",
            "a": "0",
            "m": False,
            "R": False,
            "wt": "CONTRACT_PRICE",
            "ot": "MARKET",
            "ps": "LONG",
            "cp": False,
            "rp": "0",
        },
    }
