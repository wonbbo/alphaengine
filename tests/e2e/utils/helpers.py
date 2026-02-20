"""
E2E 테스트 헬퍼 함수

테스트에서 공통으로 사용되는 유틸리티 함수.
"""

import asyncio
import time
from decimal import Decimal
from typing import Any, Callable, Awaitable

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from adapters.models import Order, OrderRequest, Position
from core.types import WebSocketState


def generate_client_order_id(prefix: str = "ae") -> str:
    """Binance 규격에 맞는 client_order_id 생성 (36자 이하)
    
    형식: {prefix}{timestamp_hex} (최대 36자)
    예: ae17a8b3c4d5e6f7
    
    Args:
        prefix: 접두사 (기본: "ae")
        
    Returns:
        36자 이하의 client_order_id
    """
    # 현재 시간 (밀리초)를 16진수로 변환하여 짧게 만듦
    timestamp_hex = hex(int(time.time() * 1000))[2:]  # '0x' 제거
    # 짧은 랜덤 부분 추가 (나노초의 일부)
    nano_part = hex(time.time_ns() % 0xFFFFFF)[2:].zfill(6)
    
    client_id = f"{prefix}{timestamp_hex}{nano_part}"
    
    # 36자 이하로 제한
    return client_id[:36]


# -------------------------------------------------------------------------
# 대기 유틸리티
# -------------------------------------------------------------------------


async def wait_for_condition(
    condition: Callable[[], Awaitable[bool]],
    timeout: float = 30.0,
    interval: float = 0.5,
    description: str = "condition",
) -> bool:
    """조건이 참이 될 때까지 대기
    
    Args:
        condition: 체크할 조건 함수 (async)
        timeout: 최대 대기 시간 (초)
        interval: 체크 간격 (초)
        description: 조건 설명 (로깅용)
        
    Returns:
        조건 충족 여부
    """
    elapsed = 0.0
    
    while elapsed < timeout:
        if await condition():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    
    return False


async def wait_for_ws_state(
    ws_client: BinanceWsClient,
    expected_state: WebSocketState,
    timeout: float = 30.0,
) -> bool:
    """WebSocket이 특정 상태가 될 때까지 대기
    
    Args:
        ws_client: WebSocket 클라이언트
        expected_state: 예상 상태
        timeout: 최대 대기 시간
        
    Returns:
        상태 도달 여부
    """
    async def check() -> bool:
        return ws_client.state == expected_state
    
    return await wait_for_condition(
        check,
        timeout=timeout,
        description=f"WebSocket state == {expected_state.value}",
    )


async def wait_for_ws_message(
    ws_client: BinanceWsClient,
    event_type: str,
    timeout: float = 60.0,
) -> dict[str, Any] | None:
    """특정 이벤트 타입의 WebSocket 메시지 대기
    
    Args:
        ws_client: WebSocket 클라이언트
        event_type: 이벤트 타입 (예: ORDER_TRADE_UPDATE)
        timeout: 최대 대기 시간
        
    Returns:
        수신된 메시지 또는 None
    """
    messages: list[dict[str, Any]] = getattr(ws_client, "_test_messages", [])
    start_idx = len(messages)
    
    async def check() -> bool:
        for msg in messages[start_idx:]:
            if msg.get("e") == event_type:
                return True
        return False
    
    if await wait_for_condition(check, timeout=timeout):
        for msg in messages[start_idx:]:
            if msg.get("e") == event_type:
                return msg
    
    return None


async def wait_for_order_status(
    rest_client: BinanceRestClient,
    symbol: str,
    order_id: str | None = None,
    client_order_id: str | None = None,
    expected_status: str | None = None,
    timeout: float = 30.0,
) -> Order | None:
    """주문이 특정 상태가 될 때까지 대기
    
    Args:
        rest_client: REST 클라이언트
        symbol: 심볼
        order_id: 거래소 주문 ID (둘 중 하나 필수)
        client_order_id: 클라이언트 주문 ID (둘 중 하나 필수)
        expected_status: 예상 상태 (None이면 아무 상태나)
        timeout: 최대 대기 시간
        
    Returns:
        주문 정보 또는 None
    """
    order: Order | None = None
    
    async def check() -> bool:
        nonlocal order
        try:
            order = await rest_client.get_order(
                symbol=symbol,
                order_id=order_id,
                client_order_id=client_order_id,
            )
            if expected_status is None:
                return True
            return order.status == expected_status
        except Exception:
            return False
    
    if await wait_for_condition(check, timeout=timeout):
        return order
    
    return None


# -------------------------------------------------------------------------
# 주문 헬퍼
# -------------------------------------------------------------------------


async def place_market_order(
    rest_client: BinanceRestClient,
    symbol: str,
    side: str,
    quantity: Decimal,
    client_order_id: str | None = None,
) -> Order:
    """시장가 주문 실행
    
    Args:
        rest_client: REST 클라이언트
        symbol: 심볼
        side: BUY / SELL
        quantity: 수량
        client_order_id: 클라이언트 주문 ID
        
    Returns:
        주문 결과
    """
    request = OrderRequest.market(
        symbol=symbol,
        side=side,
        quantity=quantity,
        client_order_id=client_order_id,
    )
    
    return await rest_client.place_order(request)


async def place_limit_order(
    rest_client: BinanceRestClient,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    client_order_id: str | None = None,
) -> Order:
    """지정가 주문 실행
    
    Args:
        rest_client: REST 클라이언트
        symbol: 심볼
        side: BUY / SELL
        quantity: 수량
        price: 가격
        client_order_id: 클라이언트 주문 ID
        
    Returns:
        주문 결과
    """
    request = OrderRequest.limit(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        client_order_id=client_order_id,
    )
    
    return await rest_client.place_order(request)


async def close_position(
    rest_client: BinanceRestClient,
    symbol: str,
) -> Order | None:
    """포지션 청산
    
    Args:
        rest_client: REST 클라이언트
        symbol: 심볼
        
    Returns:
        청산 주문 또는 None (포지션 없음)
    """
    position = await rest_client.get_position(symbol)
    
    if position is None or position.quantity == Decimal("0"):
        return None
    
    side = "SELL" if position.is_long else "BUY"
    
    request = OrderRequest.market(
        symbol=symbol,
        side=side,
        quantity=position.quantity,
        reduce_only=True,
    )
    
    return await rest_client.place_order(request)


# -------------------------------------------------------------------------
# 가격 헬퍼
# -------------------------------------------------------------------------


async def get_current_price(
    rest_client: BinanceRestClient,
    symbol: str,
) -> Decimal:
    """현재 가격 조회 (최근 체결가 기준)
    
    REST 클라이언트에 get_ticker가 없으므로 최근 체결 기록에서 가져옴.
    
    Args:
        rest_client: REST 클라이언트
        symbol: 심볼
        
    Returns:
        현재 가격
    """
    trades = await rest_client.get_trades(symbol, limit=1)
    
    if not trades:
        raise RuntimeError(f"No trades found for {symbol}")
    
    return trades[0].price


def calculate_limit_price(
    current_price: Decimal,
    side: str,
    offset_percent: Decimal = Decimal("0.01"),
) -> Decimal:
    """지정가 계산 (현재가 대비 오프셋)
    
    Args:
        current_price: 현재 가격
        side: BUY / SELL
        offset_percent: 오프셋 비율 (기본 1%)
        
    Returns:
        지정가
    """
    if side == "BUY":
        # 매수는 현재가보다 낮게 (체결 안 되게)
        return current_price * (Decimal("1") - offset_percent)
    else:
        # 매도는 현재가보다 높게 (체결 안 되게)
        return current_price * (Decimal("1") + offset_percent)


def round_price(price: Decimal, tick_size: Decimal = Decimal("0.0001")) -> Decimal:
    """가격을 tick size에 맞게 반올림
    
    Args:
        price: 원래 가격
        tick_size: 틱 사이즈
        
    Returns:
        반올림된 가격
    """
    return (price / tick_size).quantize(Decimal("1")) * tick_size


def round_quantity(qty: Decimal, step_size: Decimal = Decimal("1")) -> Decimal:
    """수량을 step size에 맞게 반올림
    
    Args:
        qty: 원래 수량
        step_size: 스텝 사이즈
        
    Returns:
        반올림된 수량
    """
    return (qty / step_size).quantize(Decimal("1")) * step_size


# -------------------------------------------------------------------------
# 검증 헬퍼
# -------------------------------------------------------------------------


async def wait_for_order_fill(
    rest_client: BinanceRestClient,
    order: Order,
    timeout: float = 30.0,
) -> Order:
    """시장가 주문 체결 대기 (Testnet 지연 대응)
    
    Testnet에서는 시장가 주문도 NEW로 반환 후 비동기 체결될 수 있음.
    REST API로 상태 폴링하여 체결 확인.
    
    Args:
        rest_client: REST 클라이언트
        order: 확인할 주문
        timeout: 최대 대기 시간
        
    Returns:
        체결된 주문 (FILLED 또는 PARTIALLY_FILLED)
        
    Raises:
        AssertionError: 타임아웃 내 체결되지 않음
    """
    if order.is_filled:
        return order
    
    filled_order = await wait_for_order_status(
        rest_client,
        symbol=order.symbol,
        order_id=order.order_id,
        expected_status="FILLED",
        timeout=timeout,
    )
    
    if filled_order and filled_order.is_filled:
        return filled_order
    
    # PARTIALLY_FILLED도 체결로 간주
    partial_order = await rest_client.get_order(order.symbol, order_id=order.order_id)
    if partial_order and partial_order.status in ("FILLED", "PARTIALLY_FILLED"):
        return partial_order
    
    raise AssertionError(
        f"Order not filled within {timeout}s: "
        f"order_id={order.order_id}, status={partial_order.status if partial_order else 'UNKNOWN'}"
    )


def assert_order_filled(order: Order) -> None:
    """주문이 체결되었는지 검증 (동기 검증, REST 폴링 없음)"""
    assert order.is_filled, f"Order not filled: status={order.status}"


def assert_order_cancelled(order: Order) -> None:
    """주문이 취소되었는지 검증"""
    assert order.is_cancelled, f"Order not cancelled: status={order.status}"


def assert_position_exists(position: Position | None) -> Position:
    """포지션이 존재하는지 검증"""
    assert position is not None, "Position not found"
    assert position.quantity > Decimal("0"), "Position quantity is zero"
    return position


def assert_no_position(position: Position | None) -> None:
    """포지션이 없는지 검증"""
    if position is not None:
        assert position.quantity == Decimal("0"), (
            f"Position exists: qty={position.quantity}"
        )
