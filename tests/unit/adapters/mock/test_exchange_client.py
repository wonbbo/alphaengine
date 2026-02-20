"""
Mock 거래소 클라이언트 테스트

MockExchangeRestClient, MockExchangeWsClient 테스트.
"""

from decimal import Decimal

import pytest
import pytest_asyncio

from adapters.mock.exchange_client import MockExchangeRestClient, MockExchangeWsClient
from adapters.models import OrderRequest
from adapters.binance.rate_limiter import OrderError
from core.types import OrderSide, OrderType, OrderStatus, WebSocketState


class TestMockExchangeRestClient:
    """MockExchangeRestClient 테스트"""
    
    @pytest.fixture
    def client(self) -> MockExchangeRestClient:
        """클라이언트 픽스처"""
        return MockExchangeRestClient()
    
    # -------------------------------------------------------------------------
    # listenKey 관리
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_create_listen_key(self, client: MockExchangeRestClient) -> None:
        """listenKey 생성"""
        listen_key = await client.create_listen_key()
        
        assert listen_key is not None
        assert listen_key.startswith("mock_listen_key_")
    
    @pytest.mark.asyncio
    async def test_extend_listen_key(self, client: MockExchangeRestClient) -> None:
        """listenKey 갱신 (에러 없이 완료)"""
        await client.extend_listen_key()
    
    @pytest.mark.asyncio
    async def test_delete_listen_key(self, client: MockExchangeRestClient) -> None:
        """listenKey 삭제"""
        await client.create_listen_key()
        await client.delete_listen_key()
        
        assert client.state.listen_key == ""
    
    # -------------------------------------------------------------------------
    # 계좌 조회
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_get_balances_default(self, client: MockExchangeRestClient) -> None:
        """기본 잔고 조회"""
        balances = await client.get_balances()
        
        assert len(balances) == 1
        assert balances[0].asset == "USDT"
        assert balances[0].wallet_balance == Decimal("10000")
    
    @pytest.mark.asyncio
    async def test_set_and_get_balance(self, client: MockExchangeRestClient) -> None:
        """잔고 설정 및 조회"""
        client.set_balance("BTC", Decimal("1.5"), Decimal("1.0"))
        
        balances = await client.get_balances()
        btc_balance = next(b for b in balances if b.asset == "BTC")
        
        assert btc_balance.wallet_balance == Decimal("1.5")
        assert btc_balance.available_balance == Decimal("1.0")
    
    @pytest.mark.asyncio
    async def test_get_position_none(self, client: MockExchangeRestClient) -> None:
        """포지션 없음"""
        position = await client.get_position("XRPUSDT")
        
        assert position is None
    
    @pytest.mark.asyncio
    async def test_set_and_get_position(self, client: MockExchangeRestClient) -> None:
        """포지션 설정 및 조회"""
        client.set_position(
            symbol="XRPUSDT",
            side="LONG",
            quantity=Decimal("1000"),
            entry_price=Decimal("0.5"),
            leverage=10,
        )
        
        position = await client.get_position("XRPUSDT")
        
        assert position is not None
        assert position.symbol == "XRPUSDT"
        assert position.side == "LONG"
        assert position.quantity == Decimal("1000")
    
    @pytest.mark.asyncio
    async def test_clear_position(self, client: MockExchangeRestClient) -> None:
        """포지션 제거"""
        client.set_position("XRPUSDT", "LONG", Decimal("100"), Decimal("0.5"))
        client.clear_position("XRPUSDT")
        
        position = await client.get_position("XRPUSDT")
        assert position is None
    
    # -------------------------------------------------------------------------
    # 주문 실행
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_place_order_success(self, client: MockExchangeRestClient) -> None:
        """주문 생성 성공"""
        request = OrderRequest.market(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            client_order_id="ae-test-001",
        )
        
        order = await client.place_order(request)
        
        assert order.order_id.startswith("mock_order_")
        assert order.client_order_id == "ae-test-001"
        assert order.status == OrderStatus.NEW.value
        assert order.original_qty == Decimal("100")
    
    @pytest.mark.asyncio
    async def test_place_order_fail_simulation(self, client: MockExchangeRestClient) -> None:
        """주문 실패 시뮬레이션"""
        client.set_fail_next_order(error_code=-2010, error_message="Test error")
        
        request = OrderRequest.market(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
        )
        
        with pytest.raises(OrderError) as exc_info:
            await client.place_order(request)
        
        assert exc_info.value.code == -2010
        assert exc_info.value.message == "Test error"
    
    @pytest.mark.asyncio
    async def test_get_open_orders(self, client: MockExchangeRestClient) -> None:
        """오픈 주문 조회"""
        # 주문 생성
        request = OrderRequest.limit(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            price=Decimal("0.5"),
        )
        await client.place_order(request)
        
        # 조회
        open_orders = await client.get_open_orders()
        
        assert len(open_orders) == 1
        assert open_orders[0].symbol == "XRPUSDT"
    
    @pytest.mark.asyncio
    async def test_get_open_orders_by_symbol(self, client: MockExchangeRestClient) -> None:
        """심볼별 오픈 주문 조회"""
        # 두 심볼에 주문 생성
        await client.place_order(OrderRequest.limit(
            symbol="XRPUSDT", side="BUY", quantity=Decimal("100"), price=Decimal("0.5")
        ))
        await client.place_order(OrderRequest.limit(
            symbol="BTCUSDT", side="BUY", quantity=Decimal("1"), price=Decimal("40000")
        ))
        
        # 심볼 필터링
        xrp_orders = await client.get_open_orders("XRPUSDT")
        
        assert len(xrp_orders) == 1
        assert xrp_orders[0].symbol == "XRPUSDT"
    
    @pytest.mark.asyncio
    async def test_cancel_order_by_order_id(self, client: MockExchangeRestClient) -> None:
        """주문 취소 (order_id)"""
        request = OrderRequest.limit(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            price=Decimal("0.5"),
        )
        order = await client.place_order(request)
        
        cancelled = await client.cancel_order("XRPUSDT", order_id=order.order_id)
        
        assert cancelled.status == OrderStatus.CANCELLED.value
    
    @pytest.mark.asyncio
    async def test_cancel_order_by_client_order_id(self, client: MockExchangeRestClient) -> None:
        """주문 취소 (client_order_id)"""
        request = OrderRequest.limit(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            price=Decimal("0.5"),
            client_order_id="ae-test-cancel",
        )
        await client.place_order(request)
        
        cancelled = await client.cancel_order(
            "XRPUSDT",
            client_order_id="ae-test-cancel",
        )
        
        assert cancelled.status == OrderStatus.CANCELLED.value
    
    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, client: MockExchangeRestClient) -> None:
        """존재하지 않는 주문 취소"""
        with pytest.raises(OrderError) as exc_info:
            await client.cancel_order("XRPUSDT", order_id="nonexistent")
        
        assert exc_info.value.code == -2011
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, client: MockExchangeRestClient) -> None:
        """모든 주문 취소"""
        # 여러 주문 생성
        await client.place_order(OrderRequest.limit(
            symbol="XRPUSDT", side="BUY", quantity=Decimal("100"), price=Decimal("0.5")
        ))
        await client.place_order(OrderRequest.limit(
            symbol="XRPUSDT", side="SELL", quantity=Decimal("50"), price=Decimal("0.6")
        ))
        
        # 모두 취소
        cancelled_count = await client.cancel_all_orders("XRPUSDT")
        
        assert cancelled_count == 2
        
        # 오픈 주문 없음 확인
        open_orders = await client.get_open_orders("XRPUSDT")
        assert len(open_orders) == 0
    
    # -------------------------------------------------------------------------
    # 체결 시뮬레이션
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_simulate_fill(self, client: MockExchangeRestClient) -> None:
        """체결 시뮬레이션"""
        request = OrderRequest.market(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
        )
        order = await client.place_order(request)
        
        # 체결
        trade = client.simulate_fill(order.order_id, fill_price=Decimal("0.5"))
        
        assert trade is not None
        assert trade.quantity == Decimal("100")
        assert trade.price == Decimal("0.5")
        
        # 주문 상태 확인
        updated_order = client.state.orders[order.order_id]
        assert updated_order.status == OrderStatus.FILLED.value
        assert updated_order.executed_qty == Decimal("100")
    
    @pytest.mark.asyncio
    async def test_simulate_partial_fill(self, client: MockExchangeRestClient) -> None:
        """부분 체결 시뮬레이션"""
        request = OrderRequest.limit(
            symbol="XRPUSDT",
            side=OrderSide.BUY.value,
            quantity=Decimal("100"),
            price=Decimal("0.5"),
        )
        order = await client.place_order(request)
        
        # 부분 체결
        client.simulate_fill(order.order_id, fill_qty=Decimal("30"))
        
        # 상태 확인
        updated_order = client.state.orders[order.order_id]
        assert updated_order.status == OrderStatus.PARTIALLY_FILLED.value
        assert updated_order.executed_qty == Decimal("30")
        assert updated_order.remaining_qty == Decimal("70")
    
    @pytest.mark.asyncio
    async def test_get_trades(self, client: MockExchangeRestClient) -> None:
        """체결 내역 조회"""
        # 주문 생성 및 체결
        order = await client.place_order(OrderRequest.market(
            symbol="XRPUSDT", side="BUY", quantity=Decimal("100")
        ))
        client.simulate_fill(order.order_id, fill_price=Decimal("0.5"))
        
        # 조회
        trades = await client.get_trades("XRPUSDT")
        
        assert len(trades) == 1
        assert trades[0].symbol == "XRPUSDT"
    
    # -------------------------------------------------------------------------
    # 설정
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_set_leverage(self, client: MockExchangeRestClient) -> None:
        """레버리지 설정"""
        result = await client.set_leverage("XRPUSDT", 20)
        
        assert result["symbol"] == "XRPUSDT"
        assert result["leverage"] == 20
    
    @pytest.mark.asyncio
    async def test_get_exchange_info(self, client: MockExchangeRestClient) -> None:
        """거래소 정보 조회"""
        info = await client.get_exchange_info()
        
        assert "symbols" in info
        assert len(info["symbols"]) >= 1


class TestMockExchangeWsClient:
    """MockExchangeWsClient 테스트"""
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        """시작 및 종료"""
        messages_received: list[dict] = []
        
        async def on_message(msg: dict) -> None:
            messages_received.append(msg)
        
        client = MockExchangeWsClient(on_message=on_message)
        
        assert client.state == WebSocketState.DISCONNECTED
        
        await client.start()
        assert client.state == WebSocketState.CONNECTED
        
        await client.stop()
        assert client.state == WebSocketState.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_inject_message(self) -> None:
        """메시지 주입"""
        messages_received: list[dict] = []
        
        async def on_message(msg: dict) -> None:
            messages_received.append(msg)
        
        client = MockExchangeWsClient(on_message=on_message)
        await client.start()
        
        # 메시지 주입
        test_message = {"e": "TEST", "data": "value"}
        await client.inject_message(test_message)
        
        # 처리 대기
        import asyncio
        await asyncio.sleep(0.2)
        
        assert len(messages_received) == 1
        assert messages_received[0]["e"] == "TEST"
        
        await client.stop()
    
    @pytest.mark.asyncio
    async def test_state_change_callback(self) -> None:
        """상태 변경 콜백"""
        state_changes: list[WebSocketState] = []
        
        async def on_message(msg: dict) -> None:
            pass
        
        async def on_state_change(state: WebSocketState) -> None:
            state_changes.append(state)
        
        client = MockExchangeWsClient(
            on_message=on_message,
            on_state_change=on_state_change,
        )
        
        await client.start()
        await client.stop()
        
        assert WebSocketState.CONNECTING in state_changes
        assert WebSocketState.CONNECTED in state_changes
        assert WebSocketState.DISCONNECTED in state_changes
    
    @pytest.mark.asyncio
    async def test_simulate_disconnect(self) -> None:
        """연결 끊김 시뮬레이션"""
        state_changes: list[WebSocketState] = []
        
        async def on_message(msg: dict) -> None:
            pass
        
        async def on_state_change(state: WebSocketState) -> None:
            state_changes.append(state)
        
        client = MockExchangeWsClient(
            on_message=on_message,
            on_state_change=on_state_change,
        )
        
        await client.start()
        await client.simulate_disconnect()
        
        assert WebSocketState.RECONNECTING in state_changes
        
        await client.stop()
