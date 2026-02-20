"""
Mock 거래소 클라이언트

테스트용 Mock REST/WebSocket 클라이언트.
IExchangeRestClient, IExchangeWsClient Protocol 준수.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Awaitable

from adapters.models import Balance, Position, Order, Trade, OrderRequest
from core.types import WebSocketState, OrderStatus, OrderSide


@dataclass
class MockState:
    """Mock 상태 (메모리 내 저장)"""
    
    # 잔고 (asset -> Balance)
    balances: dict[str, Balance] = field(default_factory=dict)
    
    # 포지션 (symbol -> Position)
    positions: dict[str, Position] = field(default_factory=dict)
    
    # 주문 (order_id -> Order)
    orders: dict[str, Order] = field(default_factory=dict)
    
    # 체결 (trade_id -> Trade)
    trades: dict[str, Trade] = field(default_factory=dict)
    
    # 오픈 주문 ID 목록
    open_order_ids: set[str] = field(default_factory=set)
    
    # 시뮬레이션 옵션
    should_fail_next_order: bool = False
    next_order_error_code: int = -1
    next_order_error_message: str = "Mock error"
    
    # listenKey
    listen_key: str = "mock_listen_key_12345"
    
    # 주문 카운터
    order_counter: int = 0
    trade_counter: int = 0


class MockExchangeRestClient:
    """Mock REST 클라이언트
    
    IExchangeRestClient Protocol 구현.
    메모리 내 상태 관리로 테스트 시나리오 지원.
    
    사용 예시:
    ```python
    client = MockExchangeRestClient()
    
    # 초기 잔고 설정
    client.set_balance("USDT", Decimal("10000"))
    
    # 주문 테스트
    order = await client.place_order(request)
    
    # 체결 시뮬레이션
    client.simulate_fill(order.order_id)
    ```
    """
    
    def __init__(self, state: MockState | None = None):
        self.state = state or MockState()
        
        # 기본 잔고 설정
        if not self.state.balances:
            self.state.balances["USDT"] = Balance(
                asset="USDT",
                wallet_balance=Decimal("10000"),
                available_balance=Decimal("10000"),
            )
    
    # -------------------------------------------------------------------------
    # 상태 조작 메서드 (테스트용)
    # -------------------------------------------------------------------------
    
    def set_balance(
        self,
        asset: str,
        wallet_balance: Decimal,
        available_balance: Decimal | None = None,
    ) -> None:
        """잔고 설정"""
        self.state.balances[asset] = Balance(
            asset=asset,
            wallet_balance=wallet_balance,
            available_balance=available_balance or wallet_balance,
        )
    
    def set_position(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
        leverage: int = 1,
    ) -> None:
        """포지션 설정"""
        self.state.positions[symbol] = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            leverage=leverage,
        )
    
    def clear_position(self, symbol: str) -> None:
        """포지션 제거"""
        if symbol in self.state.positions:
            del self.state.positions[symbol]
    
    def set_fail_next_order(
        self,
        error_code: int = -1,
        error_message: str = "Mock error",
    ) -> None:
        """다음 주문 실패 설정"""
        self.state.should_fail_next_order = True
        self.state.next_order_error_code = error_code
        self.state.next_order_error_message = error_message
    
    def simulate_fill(
        self,
        order_id: str,
        fill_qty: Decimal | None = None,
        fill_price: Decimal | None = None,
    ) -> Trade | None:
        """주문 체결 시뮬레이션"""
        if order_id not in self.state.orders:
            return None
        
        order = self.state.orders[order_id]
        
        # 체결 수량/가격 결정
        qty = fill_qty or order.remaining_qty
        price = fill_price or order.price or Decimal("1.0")
        
        # 체결 생성
        self.state.trade_counter += 1
        trade_id = f"mock_trade_{self.state.trade_counter}"
        
        trade = Trade(
            trade_id=trade_id,
            order_id=order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            quote_qty=qty * price,
            commission=qty * price * Decimal("0.0004"),
            commission_asset="USDT",
            trade_time=datetime.now(timezone.utc),
        )
        
        self.state.trades[trade_id] = trade
        
        # 주문 상태 업데이트
        new_executed_qty = order.executed_qty + qty
        new_status = (
            OrderStatus.FILLED.value
            if new_executed_qty >= order.original_qty
            else OrderStatus.PARTIALLY_FILLED.value
        )
        
        updated_order = Order(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            status=new_status,
            original_qty=order.original_qty,
            executed_qty=new_executed_qty,
            price=order.price,
            avg_price=price,
            stop_price=order.stop_price,
            time_in_force=order.time_in_force,
            reduce_only=order.reduce_only,
            created_at=order.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        
        self.state.orders[order_id] = updated_order
        
        # 체결 완료 시 오픈 주문에서 제거
        if new_status == OrderStatus.FILLED.value:
            self.state.open_order_ids.discard(order_id)
        
        return trade
    
    # -------------------------------------------------------------------------
    # listenKey 관리
    # -------------------------------------------------------------------------
    
    async def create_listen_key(self) -> str:
        """listenKey 생성"""
        self.state.listen_key = f"mock_listen_key_{uuid.uuid4().hex[:8]}"
        return self.state.listen_key
    
    async def extend_listen_key(self) -> None:
        """listenKey 갱신"""
        pass
    
    async def delete_listen_key(self) -> None:
        """listenKey 삭제"""
        self.state.listen_key = ""
    
    # -------------------------------------------------------------------------
    # 계좌 조회
    # -------------------------------------------------------------------------
    
    async def get_balances(self) -> list[Balance]:
        """잔고 목록 조회"""
        return list(self.state.balances.values())
    
    async def get_position(self, symbol: str) -> Position | None:
        """포지션 조회"""
        return self.state.positions.get(symbol)
    
    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """오픈 주문 목록 조회"""
        orders = [
            self.state.orders[oid]
            for oid in self.state.open_order_ids
            if oid in self.state.orders
        ]
        
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        
        return orders
    
    async def get_trades(
        self,
        symbol: str,
        limit: int = 500,
        start_time: int | None = None,
    ) -> list[Trade]:
        """체결 내역 조회"""
        trades = [
            t for t in self.state.trades.values()
            if t.symbol == symbol
        ]
        
        # 시간 필터링
        if start_time:
            start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
            trades = [t for t in trades if t.trade_time and t.trade_time >= start_dt]
        
        # 최신순 정렬 후 limit
        trades.sort(key=lambda t: t.trade_time or datetime.min, reverse=True)
        return trades[:limit]
    
    # -------------------------------------------------------------------------
    # 주문 실행
    # -------------------------------------------------------------------------
    
    async def place_order(self, request: OrderRequest) -> Order:
        """주문 생성"""
        # 실패 시뮬레이션
        if self.state.should_fail_next_order:
            self.state.should_fail_next_order = False
            from adapters.binance.rate_limiter import OrderError
            raise OrderError(
                code=self.state.next_order_error_code,
                message=self.state.next_order_error_message,
            )
        
        # 주문 생성
        self.state.order_counter += 1
        order_id = f"mock_order_{self.state.order_counter}"
        
        order = Order(
            order_id=order_id,
            client_order_id=request.client_order_id or f"mock_client_{order_id}",
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            status=OrderStatus.NEW.value,
            original_qty=request.quantity,
            executed_qty=Decimal("0"),
            price=request.price,
            stop_price=request.stop_price,
            time_in_force=request.time_in_force,
            reduce_only=request.reduce_only,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        self.state.orders[order_id] = order
        self.state.open_order_ids.add(order_id)
        
        return order
    
    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """주문 취소"""
        # 주문 찾기
        target_order: Order | None = None
        
        if order_id and order_id in self.state.orders:
            target_order = self.state.orders[order_id]
        elif client_order_id:
            for o in self.state.orders.values():
                if o.client_order_id == client_order_id and o.symbol == symbol:
                    target_order = o
                    break
        
        if target_order is None:
            from adapters.binance.rate_limiter import OrderError
            raise OrderError(code=-2011, message="Order not found")
        
        # 취소 처리
        cancelled_order = Order(
            order_id=target_order.order_id,
            client_order_id=target_order.client_order_id,
            symbol=target_order.symbol,
            side=target_order.side,
            order_type=target_order.order_type,
            status=OrderStatus.CANCELLED.value,
            original_qty=target_order.original_qty,
            executed_qty=target_order.executed_qty,
            price=target_order.price,
            avg_price=target_order.avg_price,
            stop_price=target_order.stop_price,
            time_in_force=target_order.time_in_force,
            reduce_only=target_order.reduce_only,
            created_at=target_order.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        
        self.state.orders[target_order.order_id] = cancelled_order
        self.state.open_order_ids.discard(target_order.order_id)
        
        return cancelled_order
    
    async def cancel_all_orders(self, symbol: str) -> int:
        """모든 주문 취소"""
        cancelled_count = 0
        
        for oid in list(self.state.open_order_ids):
            order = self.state.orders.get(oid)
            if order and order.symbol == symbol:
                await self.cancel_order(symbol, order_id=oid)
                cancelled_count += 1
        
        return cancelled_count
    
    # -------------------------------------------------------------------------
    # 설정
    # -------------------------------------------------------------------------
    
    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """레버리지 설정"""
        return {
            "symbol": symbol,
            "leverage": leverage,
            "maxNotionalValue": "10000000",
        }
    
    async def get_exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        """거래소 정보 조회"""
        symbols = [
            {
                "symbol": "XRPUSDT",
                "status": "TRADING",
                "baseAsset": "XRP",
                "quoteAsset": "USDT",
                "pricePrecision": 4,
                "quantityPrecision": 0,
            },
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "pricePrecision": 2,
                "quantityPrecision": 3,
            },
        ]
        
        if symbol:
            symbols = [s for s in symbols if s["symbol"] == symbol]
        
        return {"symbols": symbols}


# 콜백 타입 정의
MessageCallback = Callable[[dict[str, Any]], Awaitable[None]]
StateChangeCallback = Callable[[WebSocketState], Awaitable[None]]


class MockExchangeWsClient:
    """Mock WebSocket 클라이언트
    
    IExchangeWsClient Protocol 구현.
    테스트용 메시지 주입 지원.
    
    사용 예시:
    ```python
    client = MockExchangeWsClient(on_message=handle_message)
    await client.start()
    
    # 메시지 주입
    await client.inject_message({"e": "ACCOUNT_UPDATE", ...})
    
    await client.stop()
    ```
    """
    
    def __init__(
        self,
        on_message: MessageCallback,
        on_state_change: StateChangeCallback | None = None,
    ):
        self.on_message = on_message
        self.on_state_change = on_state_change
        self._state = WebSocketState.DISCONNECTED
        
        # 주입된 메시지 큐
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None
    
    @property
    def state(self) -> WebSocketState:
        """현재 연결 상태"""
        return self._state
    
    async def start(self) -> None:
        """연결 시작"""
        await self._set_state(WebSocketState.CONNECTING)
        await asyncio.sleep(0.01)  # 시뮬레이션 딜레이
        await self._set_state(WebSocketState.CONNECTED)
        
        # 메시지 처리 태스크 시작
        self._receive_task = asyncio.create_task(self._process_messages())
    
    async def stop(self) -> None:
        """연결 종료"""
        if self._receive_task is not None:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        await self._set_state(WebSocketState.DISCONNECTED)
    
    async def inject_message(self, message: dict[str, Any]) -> None:
        """테스트용 메시지 주입"""
        await self._message_queue.put(message)
    
    async def simulate_disconnect(self) -> None:
        """연결 끊김 시뮬레이션"""
        await self._set_state(WebSocketState.RECONNECTING)
        await asyncio.sleep(0.1)
        await self._set_state(WebSocketState.CONNECTED)
    
    async def _process_messages(self) -> None:
        """주입된 메시지 처리"""
        try:
            while self._state == WebSocketState.CONNECTED:
                try:
                    message = await asyncio.wait_for(
                        self._message_queue.get(),
                        timeout=0.1,
                    )
                    await self.on_message(message)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise
    
    async def _set_state(self, new_state: WebSocketState) -> None:
        """상태 변경"""
        old_state = self._state
        self._state = new_state
        
        if old_state != new_state and self.on_state_change is not None:
            await self.on_state_change(new_state)
