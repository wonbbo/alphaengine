"""
Binance API 응답 -> 공통 모델 변환

Binance Futures API 응답을 adapters.models의 표준 모델로 변환.
모든 금액/수량은 문자열에서 Decimal로 변환.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.models import Balance, Position, Order, Trade


def parse_balance(data: dict[str, Any]) -> Balance:
    """Binance 잔고 응답 -> Balance 모델
    
    Binance GET /fapi/v2/balance 응답 예시:
    {
        "accountAlias": "SgsR",
        "asset": "USDT",
        "balance": "122607.35137903",
        "crossWalletBalance": "23.72469206",
        "crossUnPnl": "0.00000000",
        "availableBalance": "23.72469206",
        "maxWithdrawAmount": "23.72469206",
        "marginAvailable": true,
        "updateTime": 1617939110373
    }
    """
    return Balance(
        asset=data["asset"],
        wallet_balance=Decimal(data["balance"]),
        available_balance=Decimal(data["availableBalance"]),
        cross_wallet_balance=Decimal(data.get("crossWalletBalance", "0")),
        unrealized_pnl=Decimal(data.get("crossUnPnl", "0")),
    )


def parse_position(data: dict[str, Any]) -> Position:
    """Binance 포지션 응답 -> Position 모델
    
    Binance GET /fapi/v2/positionRisk 응답 예시:
    {
        "symbol": "XRPUSDT",
        "positionAmt": "100",
        "entryPrice": "0.5123",
        "breakEvenPrice": "0.5125",
        "markPrice": "0.5200",
        "unRealizedProfit": "0.77",
        "liquidationPrice": "0.2500",
        "leverage": "20",
        "maxNotionalValue": "25000",
        "marginType": "cross",
        "isolatedMargin": "0.00000000",
        "isAutoAddMargin": "false",
        "positionSide": "LONG",
        "notional": "52.00",
        "isolatedWallet": "0",
        "updateTime": 1625474304765
    }
    """
    # 포지션 수량에서 방향 결정
    position_amt = Decimal(data["positionAmt"])
    
    # positionSide가 BOTH인 경우 수량 부호로 방향 결정
    position_side = data.get("positionSide", "BOTH")
    if position_side == "BOTH":
        if position_amt > Decimal("0"):
            side = "LONG"
        elif position_amt < Decimal("0"):
            side = "SHORT"
        else:
            side = "BOTH"
    else:
        side = position_side
    
    # liquidationPrice가 "0"인 경우 None 처리
    liq_price_str = data.get("liquidationPrice", "0")
    liq_price = Decimal(liq_price_str) if liq_price_str != "0" else None
    
    # markPrice
    mark_price_str = data.get("markPrice", "0")
    mark_price = Decimal(mark_price_str) if mark_price_str != "0" else None
    
    return Position(
        symbol=data["symbol"],
        side=side,
        quantity=abs(position_amt),
        entry_price=Decimal(data["entryPrice"]),
        unrealized_pnl=Decimal(data.get("unRealizedProfit", "0")),
        leverage=int(data.get("leverage", 1)),
        margin_type=data.get("marginType", "cross").upper(),
        liquidation_price=liq_price,
        mark_price=mark_price,
    )


def parse_order(data: dict[str, Any]) -> Order:
    """Binance 주문 응답 -> Order 모델
    
    Binance POST /fapi/v1/order 또는 GET /fapi/v1/openOrders 응답 예시:
    {
        "orderId": 8886774,
        "symbol": "XRPUSDT",
        "status": "NEW",
        "clientOrderId": "ae-550e8400-e29b-41d4-a716-446655440000",
        "price": "0.0000",
        "avgPrice": "0.0000",
        "origQty": "100",
        "executedQty": "0",
        "cumQuote": "0",
        "timeInForce": "GTC",
        "type": "MARKET",
        "reduceOnly": false,
        "closePosition": false,
        "side": "BUY",
        "positionSide": "LONG",
        "stopPrice": "0.0000",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": false,
        "origType": "MARKET",
        "time": 1568879465651,
        "updateTime": 1568879465651
    }
    """
    # 가격 처리 (0이면 None)
    price_str = data.get("price", "0")
    price = Decimal(price_str) if price_str != "0" else None
    
    avg_price_str = data.get("avgPrice", "0")
    avg_price = Decimal(avg_price_str) if avg_price_str != "0" else None
    
    stop_price_str = data.get("stopPrice", "0")
    stop_price = Decimal(stop_price_str) if stop_price_str != "0" else None
    
    # 시간 변환
    created_at = None
    if "time" in data:
        created_at = datetime.fromtimestamp(data["time"] / 1000, tz=timezone.utc)
    
    updated_at = None
    if "updateTime" in data:
        updated_at = datetime.fromtimestamp(data["updateTime"] / 1000, tz=timezone.utc)
    
    return Order(
        order_id=str(data["orderId"]),
        client_order_id=data.get("clientOrderId", ""),
        symbol=data["symbol"],
        side=data["side"],
        order_type=data.get("type", data.get("origType", "UNKNOWN")),
        status=data["status"],
        original_qty=Decimal(data["origQty"]),
        executed_qty=Decimal(data.get("executedQty", "0")),
        price=price,
        avg_price=avg_price,
        stop_price=stop_price,
        time_in_force=data.get("timeInForce", "GTC"),
        reduce_only=data.get("reduceOnly", False),
        created_at=created_at,
        updated_at=updated_at,
    )


def parse_trade(data: dict[str, Any]) -> Trade:
    """Binance 체결 응답 -> Trade 모델
    
    Binance GET /fapi/v1/userTrades 응답 예시:
    {
        "symbol": "XRPUSDT",
        "id": 1234567890,
        "orderId": 8886774,
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
        "maker": false,
        "buyer": true
    }
    
    또는 WebSocket ORDER_TRADE_UPDATE의 체결 부분:
    {
        "t": 1234567890,  # trade_id
        "i": 8886774,     # order_id
        "c": "ae-xxx",    # client_order_id
        "s": "XRPUSDT",   # symbol
        "S": "BUY",       # side
        "L": "0.5123",    # last price
        "l": "100",       # last qty
        "n": "0.02049",   # commission
        "N": "USDT",      # commission asset
        "T": 1568879465651,  # trade time
        "rp": "0",        # realized pnl
        "m": false        # is maker
    }
    """
    # REST API 응답과 WebSocket 응답 모두 처리
    if "id" in data:
        # REST API 응답
        trade_id = str(data["id"])
        order_id = str(data["orderId"])
        client_order_id = data.get("clientOrderId", "")
        symbol = data["symbol"]
        side = data["side"]
        price = Decimal(data["price"])
        quantity = Decimal(data["qty"])
        quote_qty = Decimal(data.get("quoteQty", str(price * quantity)))
        commission = Decimal(data.get("commission", "0"))
        commission_asset = data.get("commissionAsset", "USDT")
        realized_pnl = Decimal(data.get("realizedPnl", "0"))
        is_maker = data.get("maker", False)
        trade_time_ms = data.get("time")
    else:
        # WebSocket ORDER_TRADE_UPDATE 응답
        trade_id = str(data["t"])
        order_id = str(data["i"])
        client_order_id = data.get("c", "")
        symbol = data["s"]
        side = data["S"]
        price = Decimal(data["L"])
        quantity = Decimal(data["l"])
        quote_qty = price * quantity
        commission = Decimal(data.get("n", "0"))
        commission_asset = data.get("N", "USDT")
        realized_pnl = Decimal(data.get("rp", "0"))
        is_maker = data.get("m", False)
        trade_time_ms = data.get("T")
    
    # 시간 변환
    trade_time = None
    if trade_time_ms:
        trade_time = datetime.fromtimestamp(trade_time_ms / 1000, tz=timezone.utc)
    
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        quote_qty=quote_qty,
        commission=commission,
        commission_asset=commission_asset,
        realized_pnl=realized_pnl,
        is_maker=is_maker,
        trade_time=trade_time,
    )


def is_zero_position(data: dict[str, Any]) -> bool:
    """포지션이 0인지 확인 (필터링용)
    
    Args:
        data: Binance positionRisk 응답 항목
        
    Returns:
        수량이 0이면 True
    """
    position_amt = Decimal(data.get("positionAmt", "0"))
    return position_amt == Decimal("0")


def is_zero_balance(data: dict[str, Any]) -> bool:
    """잔고가 0인지 확인 (필터링용)
    
    Args:
        data: Binance balance 응답 항목
        
    Returns:
        잔고가 0이면 True
    """
    balance = Decimal(data.get("balance", "0"))
    return balance == Decimal("0")
